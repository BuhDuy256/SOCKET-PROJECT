import os
import sys
import time
import signal
import struct
import socket
import hashlib
import threading
import concurrent.futures
from tqdm import tqdm
from multiprocessing import Process, Queue

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
MAX_DOWLOADED_CHUNKS_EACH_TIME = 100
MAX_DOWNLOAD_FILE_RETRIES = 1

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
exit_event = threading.Event()

#------------------------------------------------------------------------------------#

def send_message_to_server(message, client_socket):
    """Sends a message to the SERVER"""
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    client_socket.sendall(header + message)

def receive_message_from_server(client_socket):
    """Receives a message from SERVER"""
    header = client_socket.recv(HEADER_SIZE).decode(ENCODE_FORMAT).strip()
    if not header:
        return None

    message_length = int(header)
    message = client_socket.recv(message_length).decode(ENCODE_FORMAT)
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
    print("Files available to download:")
    if not file_list:
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
        if file_name and 'done' not in file_name and 'in progress' not in file_name and 'failed' not in file_name:
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

def receive_chunk(file_name, start, end, client_socket):
    total_bytes_received = 0
    received_data = b""

    while total_bytes_received < end - start and not exit_event.is_set():
        header_size = struct.calcsize(f"!I {CHECKSUM_SIZE}s")
        header = client_socket.recv(header_size)
        if len(header) < header_size:
            return None

        chunk_length, checksum = struct.unpack(f"!I {CHECKSUM_SIZE}s", header)
        chunk_data = client_socket.recv(chunk_length)

        if len(chunk_data) != chunk_length:
            return None

        retries = 0
        while checksum.decode(ENCODE_FORMAT) != generate_checksum(chunk_data) and retries < 3 and not exit_event.is_set():
            retries += 1
            send_message_to_server(f"GET_NO2 {file_name} {start + total_bytes_received} {len(chunk_data)}", client_socket)
            header = client_socket.recv(header_size)
            chunk_length, checksum = struct.unpack(f"!I {CHECKSUM_SIZE}s", header)
            chunk_data = client_socket.recv(chunk_length)

        if retries == 3:
            print(f"Error: Failed to download chunk after 3 retries.")
            return None

        received_data += chunk_data
        total_bytes_received += len(chunk_data)

    return received_data

def download_chunk(file_name, start, end, max_retries=5):
    sub_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sub_client.connect(SERVER_ADDRESS)
    retries = 0

    try:
        while retries < max_retries and not exit_event.is_set():
            send_message_to_server(f"GET {file_name} {start} {end}", sub_client)
            chunk_data = receive_chunk(file_name, start, end, sub_client)

            if chunk_data:
                return chunk_data
            else:
                retries += 1
        return None
    finally:
        sub_client.close()

#######################################################################################0

def download_file(file_name, file_list):
    print(f"Downloading file: {file_name}")

def signal_handler(sig, frame):
    print("Ctrl+C pressed! Exiting...")
    exit_event.set()

def scan_and_add_to_queue_multiprocess(file_queue):
    try:
        while True:
            files_to_download = scan_input_txt()
            if files_to_download:
                for file_name in files_to_download:
                    file_queue.put(file_name)
            # else:
                # print("No files to download from input.txt")
            time.sleep(5)
    except Exception as e:
        print(f"Error in scan process: {e}")
        raise
    except KeyboardInterrupt:
        # print("Scan process interrupted.")
        return

def download_from_queue_multiprocess(current_client_id, file_queue, file_list):
    try:
        while True:
            if not file_queue.empty():
                file_name = file_queue.get()
                download_file(file_name, file_list)
    except KeyboardInterrupt:
        # print("Download process interrupted.")
        return

def main():
    scan_process = None
    download_process = None
    try:
        signal.signal(signal.SIGINT, signal_handler)
        
        client.connect(SERVER_ADDRESS)
        
        send_message_to_server(CONNECT_MESSAGE, client)

        file_list = receive_downloaded_file_list()
        display_file_list(file_list)

        file_queue = Queue()
        scan_process = Process(target=scan_and_add_to_queue_multiprocess, args=(file_queue,), daemon=True)
        download_process = Process(target=download_from_queue_multiprocess, args=(file_queue, file_list), daemon=True)

        scan_process.start()
        download_process.start()

        while scan_process.is_alive() and download_process.is_alive():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCtrl+C pressed! Terminating processes...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        send_message_to_server(DISCONNECT_MESSAGE, client)

        if scan_process and scan_process.is_alive():
            scan_process.terminate()
        if download_process and download_process.is_alive():
            download_process.terminate()

        try:
            if client:
                client.close()
        except Exception as close_error:
            print(f"Error while closing socket: {close_error}")

        print("Exiting program.")
        sys.exit(0)

if __name__ == "__main__":
    main()

