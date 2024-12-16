import os
import socket
import hashlib
import struct
import time
import sys
import signal

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 50064

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#------------------------------------------------------------------------------------#
def convert_to_bytes(size_value, size_unit):
    size_value = float(size_value)
    if size_unit == "KB":
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
    buffer_size_without_header = BUFFER_SIZE - HEADER_SIZE
    num_chunks = (total_size + buffer_size_without_header - 1) // buffer_size_without_header  # Calculate the number of chunks

    for i in range(num_chunks):
        start = i * buffer_size_without_header
        end = min((i + 1) * buffer_size_without_header, total_size)  # Ensure the last chunk doesn't exceed the total size
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
    for line in lines:
        if 'in progress' in line:
            return None
    for i, line in enumerate(lines):
        if 'done' not in line:
            file_name = line.split()[0]
            lines[i] = f"{file_name} in progress\n"
            with open("input.txt", 'w') as file:
                file.writelines(lines)
            return file_name
    return None

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
        tuple: (seq, chunk_data, checksum) if successful, or (None, None, None) if there is an error.
    """
    print(f"CHUNK: FILE_NAME={file_name}, EXPECTED_SEQ={expected_seq}, CHUNK_SIZE={chunk_size}")

    data, _ = client_socket.recvfrom(HEADER_SIZE + chunk_size)

    header = data[:HEADER_SIZE]
    seq, size, checksum = struct.unpack("!I I 16s", header)

    print(f"Received chunk header: SEQ={seq}, SIZE={size}, CHECKSUM={checksum.decode(ENCODE_FORMAT)}")

    if seq != expected_seq:
        print(f"Expected chunk {expected_seq} but received chunk {seq}.")
        return None, None, None

    if size != chunk_size:
        print(f"Expected chunk size {chunk_size} but received chunk size {size}.")
        return None, None, None

    chunk_data = data[HEADER_SIZE:]

    checksum_calculated = generate_checksum(chunk_data)

    if checksum != checksum_calculated.encode(ENCODE_FORMAT):
        print(f"Checksum mismatch for chunk {seq} of file {file_name}.")
        return None, None, None

    return seq, chunk_data, checksum


def download_chunk(file_name, seq, size):
    sub_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_message_to_server(f"GET {file_name} {seq} {size}", sub_client)
    seq, chunk_data, checksum = receive_chunk(file_name, seq, size, sub_client)
    sub_client.close()
    
    ## TODO:Handle ACK
    ## ...
    
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
    
    chunks = split_into_chunks(total_size)
    
    for seq, (start, end) in enumerate(chunks):
        chunk_size = end - start
        download_chunk(file_name, seq, chunk_size)

    ## TODO: Uncomment
    # mark_file_as_done(file_name) 
    print(f"File {file_name} downloaded successfully.")

if __name__ == "__main__":
    send_message_to_server(CONNECT_MESSAGE, client)
    file_list = receive_downloaded_file_list()
    display_file_list(file_list)
    try:
        download_file("5MB.zip", file_list)
        send_message_to_server(DISCONNECT_MESSAGE, client)
        # while True:
        #     file_name = scan_input_txt()
        #     if file_name:
        #         download_file(file_name, file_list)
        #     time.sleep(5)
    except Exception as e:
        print(f"Unexpected error: {e}")
