import os
import socket
import threading
import hashlib
import struct
import time
import sys
import signal
import re

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 5050
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'

BUFFER_SIZE = 1024

def handle_exit_signal(signum, frame):
    send_message(client, DISCONNECT_MESSAGE)
    client.close()
    sys.exit(0)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(SERVER_ADDRESS)

def send_message(connection, message):
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    connection.send(header + message)

def receive_message(connection):
    header = connection.recv(HEADER_SIZE).decode(ENCODE_FORMAT)
    if not header:
        return None
    message = connection.recv(int(header)).decode(ENCODE_FORMAT)
    return message

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:16]

def receive_chunk():
    data = client.recv(BUFFER_SIZE)
    header = data[:HEADER_SIZE]
    chunk_data = data[HEADER_SIZE:]
    seq, chunk_size, checksum = struct.unpack("!I I 16s", header[:24])
    checksum = checksum.decode('utf-8').strip('\x00')
    print(f"Received chunk {seq} with size {chunk_size} bytes and checksum {checksum}")
    return seq, chunk_data

def send_ack(seq):
    ack_message = f"ACK {seq}"
    send_message(client, ack_message)

def download_chunk(file_name, seq, size):
    send_message(client, f"GET {file_name} {seq} {size}")
    seq, chunk_data = receive_chunk()
    if chunk_data:
        with open(file_name, 'r+b') as file:
            file.seek(seq * size)
            file.write(chunk_data)
        print(f"Downloaded chunk {seq} of {file_name}")
        send_ack(seq)
    return chunk_data

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
    send_message(client, "GET FILE LIST")
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
    with open(file_name, 'wb') as file:
        file.truncate(total_size)
    threads = []
    for seq, (start, end) in enumerate(chunks):
        chunk_size = end - start
        thread = threading.Thread(target=download_chunk, args=(file_name, seq, chunk_size))
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()
    mark_file_as_done(file_name)
    print(f"File {file_name} downloaded successfully.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit_signal)
    file_list = receive_downloaded_file_list()
    display_file_list(file_list)
    try:
        while True:
            file_name = scan_input_txt()
            if file_name:
                download_file(file_name, file_list)
            time.sleep(5)
    except Exception as e:
        print(f"Unexpected error: {e}")
