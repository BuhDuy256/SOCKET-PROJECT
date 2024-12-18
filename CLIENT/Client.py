import os
import sys
import time
import queue
import signal
import struct
import socket
import hashlib
import threading
import concurrent.futures
from tqdm import tqdm

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 4096
MAX_CHUNK_SIZE = BUFFER_SIZE * 10
MAX_DOWLOADED_CHUNKS_EACH_TIME = 10
MAX_UDP_PAYLOAD_SIZE = 65507
MAX_DOWNLOAD_FILE_RETRIES = 1

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#------------------------------------------------------------------------------------#

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

def get_unique_filename(file_name):
    base_name, extension = os.path.splitext(file_name)
    counter = 1
    new_file_name = file_name

    while os.path.exists(new_file_name):
        new_file_name = f"{base_name}({counter}){extension}"
        counter += 1
    
    return new_file_name

def split_into_chunks(total_size, max_chunk_size=MAX_CHUNK_SIZE):
    chunks = []
    num_chunks = (total_size + max_chunk_size - 1) // max_chunk_size

    for i in range(num_chunks):
        start = i * max_chunk_size
        end = min((i + 1) * max_chunk_size, total_size)
        chunks.append((start, end))

    return chunks

def receive_downloaded_file_list():
    try:
        file_list_str = receive_message_from_server(client)
        file_list = []

        if file_list_str:
            file_lines = file_list_str.strip().split("\n")
            for file_line in file_lines:
                file_info = file_line.split()
                
                if len(file_info) >= 5:
                    file_name = " ".join(file_info[:-4])
                    file_size_str = file_info[-4]
                    unit = file_info[-3]
                    actual_byte = int(file_info[-2])
                    file_checksum = file_info[-1]

                    file_list.append({
                        "file_name": file_name,
                        "size_str": file_size_str,
                        "unit": unit,
                        "actual_byte": actual_byte,
                        "checksum": file_checksum
                    })

        return file_list

    except Exception as e:
        print(f"Error receiving file list: {e}")
        return []

def display_file_list(file_list):
    if not file_list:
        print("No files available to download.")
        return
    for file in file_list:
        print(f"{file['file_name']} {file['size_str']}{file['unit']}")

#------------------------------------------------------------------------------------#

def scan_input_txt():
    with open("input.txt", 'r') as file:
        lines = file.readlines()

    files_to_download = []
    
    for i, line in enumerate(lines):
        file_name = line.strip()
        if 'done' not in file_name and 'in progress' not in file_name and 'failed' not in file_name:
            files_to_download.append((file_name, i))

    if not files_to_download:
        return None

    for _, idx in files_to_download:
        lines[idx] = f"{lines[idx].strip()} in progress\n"

    with open("input.txt", 'w') as file:
        file.writelines(lines)

    return [file_name for file_name, _ in files_to_download]

def mark_file_as(file_name, status):
    try:
        with open("input.txt", 'r') as file:
            lines = file.readlines()
        for i, line in enumerate(lines):
            if line.startswith(file_name) and 'in progress' in line:
                if status == "done":
                    lines[i] = f"{file_name} done\n"
                    print(f"Marked file {file_name} as done.")
                elif status == "failed":
                    lines[i] = f"{file_name} failed\n"
                    print(f"Marked file {file_name} as failed.")
                break
        with open("input.txt", 'w') as file:
            file.writelines(lines)
    except Exception as e:
        print(f"An error occurred while marking file {file_name} as done: {e}")

#------------------------------------------------------------------------------------#

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:CHECKSUM_SIZE]

def generate_file_checksum(file_name):
    md5_hash = hashlib.md5()
    try:
        with open(file_name, "rb") as f:
            for chunk in iter(lambda: f.read(BUFFER_SIZE), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except FileNotFoundError:
        return f"Error: File '{file_name}' not found."
    except Exception as e:
        return f"Error: {e}"

def receive_chunk(file_name, expected_seq, chunk_size, client_socket):
    data, _ = client_socket.recvfrom(HEADER_SIZE)
    header = data[:(4 + 4 + CHECKSUM_SIZE)]
    seq, size, checksum = struct.unpack("!I I 16s", header)

    if seq != expected_seq:
        print(f"Expected chunk {expected_seq} but received chunk {seq}.")
        return None, None

    if size != chunk_size:
        print(f"Expected chunk size {chunk_size} but received chunk size {size}.")
        return None, None

    received_data = b""
    while len(received_data) < size:
        part_data, _ = client_socket.recvfrom(BUFFER_SIZE)
        received_data += part_data

    checksum_calculated = generate_checksum(received_data)
    if checksum.decode(ENCODE_FORMAT) != checksum_calculated:
        print(f"Checksum mismatch for chunk {seq} of file {file_name}.")
        time.sleep(5)
        return None, None

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
                time.sleep(5)
        
        return None, None
    finally:
        sub_client.close()

#------------------------------------------------------------------------------------#

lock = threading.Lock()

def download_file(file_name, file_list):
    file_info = None

    for file in file_list:
        if file["file_name"] == file_name:
            file_info = file
            break

    if not file_info:
        print(f"File {file_name} is not in the list.")
        return

    total_size = file_info["actual_byte"]
    print("Total size of the file:", total_size)

    new_file_name = get_unique_filename(file_name)
    print(f"Saving file as: {new_file_name}")

    chunks = split_into_chunks(total_size)

    retries = 0
    while retries < MAX_DOWNLOAD_FILE_RETRIES:
        chunk_data_dict = {}

        try:
            with tqdm(total=len(chunks), desc=f"Downloading {new_file_name}", unit="chunk") as download_bar:
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWLOADED_CHUNKS_EACH_TIME) as executor:
                    futures = []

                    for expected_seq, (start, end) in enumerate(chunks):
                        chunk_size = end - start
                        futures.append(executor.submit(download_chunk, file_name, expected_seq, chunk_size))

                        if len(futures) == MAX_DOWLOADED_CHUNKS_EACH_TIME or expected_seq == len(chunks) - 1:
                            concurrent.futures.wait(futures)

                            for future in futures:
                                seq, chunk_data = future.result()
                                if seq is not None and chunk_data is not None:
                                    with lock:
                                        chunk_data_dict[seq] = chunk_data
                                    download_bar.update(1)

                            futures = []

            with tqdm(total=len(chunks), desc=f"Merging {new_file_name}", unit="chunk") as merge_bar:
                with open(new_file_name, "wb") as file:
                    for seq in sorted(chunk_data_dict.keys()):
                        file.write(chunk_data_dict[seq])
                        merge_bar.update(1)

            server_file_checksum = file_info["checksum"]
            new_file_checksum = generate_file_checksum(new_file_name)

            if new_file_checksum == server_file_checksum:
                print(f"File {file_name} downloaded and merged as {new_file_name} successfully.")
                mark_file_as(file_name, "done")
                break
            else:
                print(f"Checksum mismatch for file {file_name}.")
                os.remove(new_file_name)
                retries += 1
                time.sleep(5)

        except Exception as e:
            print(f"Error downloading file {file_name}, attempt {retries + 1}/{MAX_DOWNLOAD_FILE_RETRIES}: {e}")
            retries += 1
            time.sleep(5)

    if retries == MAX_DOWNLOAD_FILE_RETRIES:
        print(f"Failed to download file {file_name} after {MAX_DOWNLOAD_FILE_RETRIES} attempts.")
        mark_file_as(file_name, "failed")

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

def signal_handler(sig, frame):
    print("Ctrl+C pressed! Exiting...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

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
