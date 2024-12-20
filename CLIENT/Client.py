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
GET_DOWLOADED_FILES_LIST_MESSAGE = 'GET DOWLOADED FILES LIST'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 4096
MAX_CHUNK_SIZE = BUFFER_SIZE * 10
MAX_DOWLOADED_CHUNKS_EACH_TIME = 100
MAX_UDP_PAYLOAD_SIZE = 65507
MAX_DOWNLOAD_FILE_RETRIES = 1

CLIENT_ID_LENGTH = 26 # FIX
DEFAULT_CLIENT_ID = '23127006_23127179_23127189'

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
exit_event = threading.Event()

#------------------------------------------------------------------------------------#

def send_message_to_server(message, client_id, client_socket):
    client_id_encoded = client_id.encode(ENCODE_FORMAT)
    message_encoded = message.encode(ENCODE_FORMAT)

    combined_message = client_id_encoded + b"|" + message_encoded

    header = f"{len(combined_message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)

    client_socket.sendto(header + combined_message, SERVER_ADDRESS)


def receive_message_from_server(client_socket):
    data, _ = client_socket.recvfrom(BUFFER_SIZE)

    header = data[:HEADER_SIZE].decode(ENCODE_FORMAT).strip()
    if not header:
        return None, None

    combined_message = data[HEADER_SIZE:HEADER_SIZE + int(header)]
    client_id, message = combined_message.split(b"|", 1)

    client_id = client_id.decode(ENCODE_FORMAT)
    message = message.decode(ENCODE_FORMAT)

    return message, client_id

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

def receive_downloaded_file_list(current_client_id):
    try:
        file_list_str, client_id = receive_message_from_server(client)

        if client_id != current_client_id:
            print(f"Error: Client ID mismatch. Expected: {current_client_id}, Received: {client_id}")
            return []

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

def receive_chunk(file_name, start, end, current_client_id, client_socket):
    total_bytes_received = 0
    received_data = b""

    while total_bytes_received < end - start and not exit_event.is_set():
        packet, addr = client_socket.recvfrom(MAX_UDP_PAYLOAD_SIZE)

        header_size = struct.calcsize(f"!I {CHECKSUM_SIZE}s")
        if len(packet) < header_size:
            # print("Error: Packet too small to contain header.")
            return None

        chunk_length, checksum = struct.unpack(f"!I {CHECKSUM_SIZE}s", packet[:header_size])
        chunk_data = packet[header_size:]

        if len(chunk_data) != chunk_length:
            # print("Error: Length of received chunk data does not match with chunk length in header.")
            return None

        retries = 0
        while checksum.decode(ENCODE_FORMAT) != generate_checksum(chunk_data) and retries < 3 and not exit_event.is_set():
            # print(f"Checksum mismatch for chunk starting at {start + total_bytes_received}. Retrying...")
            chunk_start = start + total_bytes_received

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as retry_client:
                retry_client.settimeout(5)

                try:
                    send_message_to_server(f"GET_NO2 {file_name} {chunk_start} {len(chunk_data)}", current_client_id, retry_client)
                    retry_packet, addr = retry_client.recvfrom(MAX_UDP_PAYLOAD_SIZE)
                except socket.timeout:
                    # print(f"Error: Timeout while receiving retry packet for chunk starting at {chunk_start}.")
                    retries += 1
                    continue

                retry_header_size = struct.calcsize(f"!I {CHECKSUM_SIZE}s")
                if len(retry_packet) < retry_header_size:
                    # print("Error: Packet too small during retry.")
                    return None

                retry_chunk_length, checksum = struct.unpack(f"!I {CHECKSUM_SIZE}s", retry_packet[:retry_header_size])
                chunk_data = retry_packet[retry_header_size:]

                if len(chunk_data) != retry_chunk_length:
                    # print("Error: Length of received chunk data does not match with chunk length in header during retry.")
                    retries += 1
                    continue 

            retries += 1

        if retries == 3:
            print(f"Error: Failed to download chunk after 3 retries.")
            return None

        received_data += chunk_data
        total_bytes_received += len(chunk_data)

    return received_data

def download_chunk(current_client_id, file_name, start, end, max_retries=5):
    sub_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    retries = 0

    try:
        while retries < max_retries and not exit_event.is_set():
            send_message_to_server(f"GET {file_name} {start} {end}", current_client_id, sub_client)
            chunk_data = receive_chunk(file_name, start, end, current_client_id, sub_client)

            if chunk_data:
                return chunk_data
            else:
                retries += 1
        return None
    finally:
        sub_client.close()

#------------------------------------------------------------------------------------#

lock = threading.Lock()

def download_file(current_client_id, file_name, file_list):
    file_info = None

    for file in file_list:
        if file["file_name"] == file_name:
            file_info = file
            break

    if not file_info:
        print(f"File {file_name} is not in the list.")
        mark_file_as(file_name, "failed")
        return

    total_size = file_info["actual_byte"]
    print("Total size of the file:", total_size)

    new_file_name = get_unique_filename(file_name)
    print(f"Saving file as: {new_file_name}")

    chunks = split_into_chunks(total_size)

    retries = 0
    while retries < MAX_DOWNLOAD_FILE_RETRIES and not exit_event.is_set():
        chunk_data_dict = {}

        try:
            with tqdm(total=len(chunks), desc=f"Downloading {new_file_name}", unit="chunk") as download_bar:
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWLOADED_CHUNKS_EACH_TIME) as executor:
                    futures = {
                        executor.submit(download_chunk, current_client_id, file_name, start, end): seq
                        for seq, (start, end) in enumerate(chunks)
                    }

                    for future in concurrent.futures.as_completed(futures):
                        seq = futures[future]
                        try:
                            chunk_data = future.result()
                            if chunk_data is not None:
                                with lock:
                                    chunk_data_dict[seq] = chunk_data
                                download_bar.update(1)
                            else:
                                print(f"Failed to download chunk {seq}. Stopping download process...")
                                raise ValueError(f"Chunk {seq} is None. Aborting file download.")
                        except Exception as e:
                            print(f"Error downloading chunk {seq}: {e}")
                            raise

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
                print(f"Checksum mismatch for file {file_name}. Retrying...")
                os.remove(new_file_name)
                retries += 1
                time.sleep(0.1)

        except Exception as e:
            print(f"Error downloading file {file_name}, attempt {retries + 1}/{MAX_DOWNLOAD_FILE_RETRIES}: {e}")
            retries += 1
            time.sleep(0.1)
            break

    if retries == MAX_DOWNLOAD_FILE_RETRIES or len(chunk_data_dict) < len(chunks):
        print(f"Failed to download file {file_name} after {MAX_DOWNLOAD_FILE_RETRIES} attempts.")
        mark_file_as(file_name, "failed")
        if os.path.exists(new_file_name):
            os.remove(new_file_name)

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
                download_file(current_client_id, file_name, file_list)
    except KeyboardInterrupt:
        # print("Download process interrupted.")
        return

def main():
    scan_process = None
    download_process = None
    current_client_id = None

    try:
        signal.signal(signal.SIGINT, signal_handler)

        send_message_to_server(CONNECT_MESSAGE, DEFAULT_CLIENT_ID, client)
        response, client_id = receive_message_from_server(client)

        if response == "BUSY":
            print("Server is busy. Please try again later.")
            return
        else:
            print("Connected to server.")
            current_client_id = response

        # print("Current client ID:", current_client_id)

        send_message_to_server(GET_DOWLOADED_FILES_LIST_MESSAGE, current_client_id, client)
        file_list = receive_downloaded_file_list(current_client_id)
        display_file_list(file_list)

        file_queue = Queue()
        scan_process = Process(target=scan_and_add_to_queue_multiprocess, args=(file_queue,), daemon=True)
        download_process = Process(target=download_from_queue_multiprocess, args=(current_client_id, file_queue, file_list), daemon=True)

        scan_process.start()
        download_process.start()

        while scan_process.is_alive() and download_process.is_alive():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCtrl+C pressed! Terminating processes...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        send_message_to_server(DISCONNECT_MESSAGE, current_client_id, client)

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
