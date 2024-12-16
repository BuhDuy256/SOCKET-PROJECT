import os
import socket
import hashlib
import struct
import time
import sys
import signal

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 5050
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'

BUFFER_SIZE = 4096

def handle_exit_signal(signum, frame):
    send_message(client, DISCONNECT_MESSAGE)
    client.close()
    sys.exit(0)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(SERVER_ADDRESS)

def send_message(connection, message):
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    connection.sendall(header)
    connection.sendall(message)

def receive_message(connection):
    header = connection.recv(HEADER_SIZE).decode(ENCODE_FORMAT)
    if not header:
        return None
    message = connection.recv(int(header)).decode(ENCODE_FORMAT)
    return message

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

def split_into_chunks(total_size, num_chunks=4):
    chunk_size = total_size // num_chunks
    chunks = []
    
    for i in range(num_chunks):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < num_chunks - 1 else total_size
        chunks.append((start, end))

    return chunks

def receive_downloaded_file_list():
    file_list_str = receive_message(client)
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

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:16]

def receive_chunk(connection, file_name, expected_seq, chunk_size):
    print(f"CHUNK: FILE_NAME={file_name}, EXPECTED_SEQ={expected_seq}, CHUNK_SIZE={chunk_size}")
    
    header = connection.recv(HEADER_SIZE)
    
    if len(header) < 24:
        print("Header size is smaller than expected.")
        return None, None, None  # Handle the error properly

    seq, size, checksum = struct.unpack("!I I 16s", header[0:24])  # Unpack header

    print(f"Received chunk header: SEQ={seq}, SIZE={size}, CHECKSUM={checksum}")

    if seq != expected_seq:
        print(f"Expected chunk {expected_seq} but received chunk {seq}.")
        return None, None, None

    if size != chunk_size:
        print(f"Expected chunk size {chunk_size} but received chunk size {size}.")
        return None, None, None

    chunk_data = b""
    while len(chunk_data) < size:
        data = connection.recv(min(BUFFER_SIZE, size - len(chunk_data)))
        if not data:
            print(f"Error: Connection closed unexpectedly while receiving chunk data for {file_name}")
            return None, None, None
        chunk_data += data

    checksum_calculated = generate_checksum(chunk_data)

    if checksum != checksum_calculated.encode(ENCODE_FORMAT):
        print(f"Checksum mismatch for chunk {seq} of file {file_name}.")
        return None, None, None

    return seq, chunk_data, checksum

def download_chunk(file_name, seq, size):
    while True:
        send_message(client, f"GET {file_name} {seq} {size}")
        seq, chunk_data, checksum = receive_chunk(client, file_name, seq, size)
        
        # Handle ACK
        if (seq is not None) and (chunk_data is not None) and (checksum is not None):
            send_message(client, f"ACK {seq}")
            break
    
    
    # TODO: The thread error because of this line, if many threads are running at the same time, the file will be corrupted
    # if chunk_data:
    #     with open(file_name, 'r+b') as file:
    #         print(f"Writing chunk {seq} to file {file_name}.")
    #         file.seek(seq * size)
    #         file.write(chunk_data)
    
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

    # TODO: Uncomment    
    # with open(file_name, 'wb') as file:
    #     file.truncate(total_size)
    
    for seq, (start, end) in enumerate(chunks):
        chunk_size = end - start
        download_chunk(file_name, seq, chunk_size)

    ## TODO: Uncomment
    # mark_file_as_done(file_name) 
    print(f"File {file_name} downloaded successfully.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit_signal)
    file_list = receive_downloaded_file_list()
    display_file_list(file_list)
    try:
        download_file("5MB.zip", file_list)
        send_message(client, DISCONNECT_MESSAGE)
        # while True:
        #     file_name = scan_input_txt()
        #     if file_name:
        #         download_file(file_name, file_list)
        #     time.sleep(5)
    except Exception as e:
        print(f"Unexpected error: {e}")
