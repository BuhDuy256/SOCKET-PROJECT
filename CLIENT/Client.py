import os
import socket
import hashlib
import struct
import time
import concurrent.futures
from tqdm import tqdm
import queue
import threading

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 1024
MAX_UDP_PAYLOAD_SIZE = BUFFER_SIZE * 10
MAX_DOWLOADED_CHUNKS_EACH_TIME = 5

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#------------------------------------------------------------------------------------#
def convert_to_bytes(size_value, size_unit):
    size_value = float(size_value)
    if (size_unit == "B"):
        return int(size_value)
    elif size_unit == "KB":
        return int(size_value * 1024)
    elif size_unit == "MB":
        return int(size_value * 1024 * 1024)
    elif size_unit == "GB":
        return int(size_value * 1024 * 1024 * 1024)
    else:
        raise ValueError("Unknown size unit")

def send_message_to_server(message, client_socket):
    """Sends a message to the SERVER"""
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    client_socket.sendto(header + message, SERVER_ADDRESS)

def receive_message_from_server(client_socket):
    """Receives a message from SERVER"""
    data, _ = client_socket.recvfrom(BUFFER_SIZE)
    header = data[:HEADER_SIZE].decode(ENCODE_FORMAT).strip()

    if not header:
        return None

    message = data[HEADER_SIZE:HEADER_SIZE + int(header)].decode(ENCODE_FORMAT)
    return message

def split_into_chunks(total_size):
    """
    Splits a file into chunks based on the buffer size.

    Args:
        total_size (int): The total size of the file in bytes.
        buffer_size (int): The size of each chunk in bytes.

    Returns:
        list: A list of tuples, where each tuple contains the start and end byte positions of a chunk.
    """
    chunks = []
    num_chunks = (total_size + MAX_UDP_PAYLOAD_SIZE - 1) // MAX_UDP_PAYLOAD_SIZE  # Calculate the number of chunks

    for i in range(num_chunks):
        start = i * MAX_UDP_PAYLOAD_SIZE
        end = min((i + 1) * MAX_UDP_PAYLOAD_SIZE, total_size)  # Ensure the last chunk doesn't exceed the total size
        chunks.append((start, end))

    return chunks

def receive_downloaded_file_list():
    file_list_str = receive_message_from_server(client)
    file_list = []
    if file_list_str:
        file_lines = file_list_str.strip().split("\n")
        for file_line in file_lines:
            file_info = file_line.split()
            if len(file_info) >= 2:
                file_name = file_info[0]
                file_size = " ".join(file_info[1:])
                size_value, size_unit = file_size.split()
                file_list.append({
                    "file_name": file_name,
                    "size_value": size_value,
                    "size_unit": size_unit
                })
    return file_list

def display_file_list(file_list):
    if not file_list:
        print("No files available to download.")
        return
    for file in file_list:
        print(f"{file['file_name']} {file['size_value']}{file['size_unit']}")
#------------------------------------------------------------------------------------#

#------------------------------------------------------------------------------------#
def scan_input_txt():
    with open("input.txt", 'r') as file:
        lines = file.readlines()

    files_to_download = []
    
    # Filter files that are not marked 'done' or 'in progress'
    for i, line in enumerate(lines):
        file_name = line.strip()  # Remove whitespace and newline
        if 'done' not in file_name and 'in progress' not in file_name:
            files_to_download.append((file_name, i))

    # If there are no files to download, return None
    if not files_to_download:
        return None
    
    # Mark these files as 'in progress'
    for _, idx in files_to_download:
        lines[idx] = f"{lines[idx].strip()} in progress\n"
    
    # Save the changes back to input.txt
    with open("input.txt", 'w') as file:
        file.writelines(lines)

    # Return the list of files to download
    return [file_name for file_name, _ in files_to_download]


def mark_file_as_done(file_name):
    try:
        with open("input.txt", 'r') as file:
            lines = file.readlines()
        for i, line in enumerate(lines):
            if line.startswith(file_name) and 'in progress' in line:
                lines[i] = f"{file_name} done\n"
                break
        with open("input.txt", 'w') as file:
            file.writelines(lines)
        print(f"File {file_name} has been marked as done.")
    except Exception as e:
        print(f"An error occurred while marking file {file_name} as done: {e}")
#------------------------------------------------------------------------------------#

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:16]

def receive_chunk(file_name, expected_seq, chunk_size, client_socket):
    """
    Receives a chunk of a file from the server and verifies its header and data.

    Args:
        file_name (str): The name of the file being received.
        expected_seq (int): The expected sequence number of the chunk.
        chunk_size (int): The size of each chunk.
        client_socket (socket.socket): The socket used for communication.

    Returns:
        tuple: (seq, chunk_data) if successful, or (None, None) if there is an error.
    """
    
    # Receive the header of the first chunk
    data, _ = client_socket.recvfrom(HEADER_SIZE)
    header = data[:(4 + 4 + CHECKSUM_SIZE)]
    seq, size, checksum = struct.unpack("!I I 16s", header)

    # print (f"Received chunk {seq} of file {file_name} with size: {size} bytes, checksum: {checksum}")

    # Check if the sequence number of the chunk does not match
    if seq != expected_seq:
        print(f"Expected chunk {expected_seq} but received chunk {seq}.")
        return None, None

    if size != chunk_size:
        print(f"Expected chunk size {chunk_size} but received chunk size {size}.")
        return None, None

    # Receive the data of the chunk (in parts of BUFFER_SIZE bytes)
    received_data = b""
    while len(received_data) < size:
        part_data, _ = client_socket.recvfrom(BUFFER_SIZE)  # Receive small parts of data
        received_data += part_data

    # Verify the checksum
    checksum_calculated = generate_checksum(received_data)
    if checksum != checksum_calculated.encode(ENCODE_FORMAT):
        print(f"Checksum mismatch for chunk {seq} of file {file_name}.")
        return None, None

    # Return valid chunk information
    return seq, received_data

def download_chunk(file_name, seq, size, max_retries=5):
    sub_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    retries = 0
    
    try:
        while retries < max_retries:
            send_message_to_server(f"GET {file_name} {seq} {size}", sub_client)
            seq_received, chunk_data = receive_chunk(file_name, seq, size, sub_client)

            if seq_received is not None and chunk_data is not None:
                return seq_received, chunk_data
            else:
                print(f"Retrying chunk {seq} of file {file_name}...")
                retries += 1
                time.sleep(5)  # Wait before retrying
        
        return None, None
    finally:
        sub_client.close()

def get_unique_filename(file_name):
    """Checks if a file already exists on the local system and adds a number to the name if it does."""
    base_name, extension = os.path.splitext(file_name)
    counter = 1
    new_file_name = file_name
    
    # Check if the file exists, and if so, increment the counter in the filename
    while os.path.exists(new_file_name):
        new_file_name = f"{base_name}({counter}){extension}"
        counter += 1
    
    return new_file_name

def download_file(file_name, file_list):
    file_info = None

    for file in file_list:
        if file["file_name"] == file_name:
            file_info = file
            break

    if not file_info:
        print(f"File {file_name} is not in the list.")
        return
    
    total_size = convert_to_bytes(file_info["size_value"], file_info["size_unit"])
    print(f"Total size of {file_name}: {total_size} bytes")
    
    # Get a unique file name if the file already exists on the local machine
    new_file_name = get_unique_filename(file_name)
    print(f"Saving file as: {new_file_name}")
    
    chunks = split_into_chunks(total_size)
    chunk_data_dict = {}  # Dictionary to store chunk data by sequence number
    
    # Progress bar for downloading chunks
    with tqdm(total=len(chunks), desc=f"Downloading {new_file_name}", unit="chunk") as download_bar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWLOADED_CHUNKS_EACH_TIME) as executor:
            futures = []
            
            # Download chunks in parallel
            for seq, (start, end) in enumerate(chunks):
                chunk_size = end - start
                futures.append(executor.submit(download_chunk, file_name, seq, chunk_size))

                # Wait for chunks to be downloaded in batches of 5
                if len(futures) >= MAX_DOWLOADED_CHUNKS_EACH_TIME:
                    concurrent.futures.wait(futures)
                    
                    for future in futures:
                        seq, chunk_data = future.result()  # Get the result from the future
                        
                        if seq is not None:
                            chunk_data_dict[seq] = chunk_data  # Store the chunk data by seq
                            download_bar.update(1)  # Update progress bar
                        
                    futures = []  # Reset futures list
            
            # Wait for the remaining chunks to be downloaded
            concurrent.futures.wait(futures)
            
            for future in futures:
                seq, chunk_data = future.result()  # Get the result from the future
                
                if seq is not None:
                    chunk_data_dict[seq] = chunk_data  # Store the chunk data by seq
                    download_bar.update(1)  # Update progress bar

    # Create the file with fixed size before writing
    with open(file_name, 'wb') as f:
        f.truncate(total_size)  # Create the file with the fixed size

    # Progress bar for merging chunks
    with tqdm(total=len(chunks), desc=f"Merging {new_file_name}", unit="chunk") as merge_bar:
        # Open the file to write chunks in the correct order
        with open(new_file_name, 'r+b') as file:  # Open in 'r+b' mode to read and write binary
            for seq in sorted(chunk_data_dict.keys()):
                file.seek(seq * MAX_UDP_PAYLOAD_SIZE)  # Move to the correct position based on the chunk sequence
                file.write(chunk_data_dict[seq])  # Write the chunk data to the correct position
                merge_bar.update(1)  # Update progress bar
    
    print(f"File {file_name} downloaded and merged as {new_file_name} successfully.")

def scan_and_add_to_queue(file_queue):
    while True:
        files_to_download = scan_input_txt()
        if files_to_download:
            for file_name in files_to_download:
                file_queue.put(file_name)

        time.sleep(5)

def download_from_queue(file_queue, file_list):
    while True:
        if not file_queue.empty():
            file_name = file_queue.get()
            download_file(file_name, file_list)
            mark_file_as_done(file_name)

if __name__ == "__main__":
    send_message_to_server(CONNECT_MESSAGE, client)
    file_list = receive_downloaded_file_list()
    display_file_list(file_list)
    try:
        file_queue = queue.Queue()

        scan_thread = threading.Thread(target=scan_and_add_to_queue, args=(file_queue,))
        scan_thread.daemon = True
        scan_thread.start()

        download_thread = threading.Thread(target=download_from_queue, args=(file_queue, file_list))
        download_thread.daemon = True
        download_thread.start()

        scan_thread.join()
        download_thread.join()

    except Exception as e:
        print(f"Unexpected error: {e}")
