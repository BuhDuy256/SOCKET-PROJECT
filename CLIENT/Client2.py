import socket
import threading
from tqdm import tqdm
import hashlib
import os
import time
import struct
import signal
import sys
from multiprocessing import Process, Queue


CHUNK_SIZE = 1024  # 1 KB
NUM_THREADS = 4
SERVER_IP = "192.168.100.51"
SERVER_PORT = 12345

# ----------------- SIGNAL HANDLER -----------------
exit_event = threading.Event()

def signal_handler(sig, frame):
    print("Exiting...")
    exit_event.set()


# ----------------- DOWNLOADER & MERGING -----------------


def calculate_checksum(data):
    """
    SHA-256 to calculate checksum of data.
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(data)
    return hash_obj.hexdigest()


def download_chunk(server_ip, server_port, file_name, start, end, part_index, progress_bar):
    """
    Download a part of the file from the server.
    """
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((server_ip, server_port))
        
        # Send request to server
        request = f"GET {file_name} {start} {end}\n"
        client_socket.send(request.encode())
        
        with open(f"part_{part_index}.tmp", "wb") as part_file:
            total_bytes_received = 0
            while total_bytes_received < (end - start) and not exit_event.is_set():
                # Receive chunk header
                header = client_socket.recv(4)
                if not header:
                    break
                chunk_length = struct.unpack("!I", header)[0]
                
                # Receive chunk data and checksum
                data = client_socket.recv(chunk_length)
                checksum_data = client_socket.recv(64)
                try:
                    checksum = checksum_data.decode("utf-8")
                except UnicodeDecodeError:
                    print(f"Thread {part_index}: Received invalid checksum: {checksum_data}")
                    return  # Ngừng nếu checksum không hợp lệ

                
                times = 0
                # Check checksum, retry if mismatch up to 3 times
                while calculate_checksum(data) != checksum and times < 3:
                    print(f"Thread {part_index}: CHECKSUM mismatch. Retrying...")
                    chunk_start = start + total_bytes_received
                    retry_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    retry_client.connect((server_ip, server_port))
                    retry_request = f"GET_CHUNK {chunk_start} {chunk_length}\n"
                    retry_client.send(retry_request.encode())
                    
                    # Receive chunk data and checksum again
                    retry_header = retry_client.recv(4)
                    retry_chunk_length = struct.unpack("!I", retry_header)[0]
                    data = retry_client.recv(retry_chunk_length)
                    checksum = retry_client.recv(64).decode()
                    times += 1
                    
                    
                    
                    retry_client.close()
                # Write data to file
                part_file.write(data)
                total_bytes_received += len(data)
                progress_bar.update(len(data))
        
        client_socket.close()
    except Exception as e:
        print(f"Error at thread {part_index}: {e}")
    finally:
        client_socket.close()


def merge_files(file_name, num_parts):
    """
    Merge all parts of the file into one file.
    """
    with open(file_name, "wb") as output_file:
        for i in range(num_parts):
            part_file = f"part_{i}.tmp"
            with open(part_file, "rb") as pf:
                output_file.write(pf.read())
            os.remove(part_file)


def download_file(server_ip, server_port, file_name):
    """
    Download file from server.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((server_ip, server_port))
    client_socket.send(f"SIZE {file_name}\n".encode())
    file_size = int(client_socket.recv(1024).decode())
    client_socket.close()

    print(f"File size: {file_size} bytes")
    
    # Split file into chunks
    chunk_size = file_size // NUM_THREADS
    threads = []
    progress_bars = []

    for i in range(NUM_THREADS):
        start = i * chunk_size
        end = start + chunk_size if i < NUM_THREADS - 1 else file_size
        progress_bar = tqdm(total=(end - start), desc=f"Thread {i}", unit="B", unit_scale=True)
        progress_bars.append(progress_bar)
        thread = threading.Thread(target=download_chunk, args=(server_ip, server_port, file_name, start, end, i, progress_bar))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    for progress_bar in progress_bars:
        progress_bar.close()

    print("Merging parts...")
    merge_files("downloaded_" + file_name, NUM_THREADS)
    print(f"Download complete: downloaded_{file_name}")


# ----------------- SCANNER -----------------


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
    except KeyboardInterrupt:
        print("\nCtrl C is pressed...")
        return

def scan_and_add_to_queue(file_queue):
    while not exit_event.is_set():
        files_to_download = scan_input_txt()
        if files_to_download:
            for file_name in files_to_download:
                file_queue.put(file_name)

        time.sleep(5)

#----------------- CLIENT -----------------


def get_allow_download_list(server_ip, server_port):
    list = []
    download_file(server_ip, server_port, "allow_download.txt")
    with open("downloaded_allow_download.txt", 'r') as file:
        lines = file.readlines()
        for line in lines:

            file_name, _= line.strip().split()
            list.append(file_name)
    os.remove("downloaded_allow_download.txt")
    return list

def display_file_list(file_list):
    if not file_list:
        print("No files available to download.")
        return
    print("List of files available to download:")
    for file in file_list:
        print(file)

def download_from_queue(file_queue, file_list):
    try:
        while not exit_event.is_set():
            if not file_queue.empty():
                file_name = file_queue.get()
                if file_name in file_list:
                    download_file(SERVER_IP, SERVER_PORT, file_name)
                else:
                    print(f"File {file_name} is not in the allow list.")
                mark_file_as_done(file_name)
    except KeyboardInterrupt:
        print("\nCtrl C is pressed...")
        return
        


def main():
    allow_files = get_allow_download_list(SERVER_IP, SERVER_PORT)
    display_file_list(allow_files)

    try:
        # Đăng ký tín hiệu Ctrl+C
        signal.signal(signal.SIGINT, signal_handler)
        
        file_queue = Queue()
        
        # Tạo và khởi chạy các luồng
        scan_thread = threading.Thread(target=scan_and_add_to_queue, args=(file_queue,))
        download_thread = threading.Thread(target=download_from_queue, args=(file_queue, allow_files))
        
        scan_thread.start()
        download_thread.start()
        
        # Chờ luồng chính chạy cho đến khi `exit_event` được kích hoạt
        while not exit_event.is_set():
            time.sleep(1)

        print("Waiting for threads to exit...")

        # Đợi các luồng kết thúc
        scan_thread.join(timeout=2)
        download_thread.join(timeout=2)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Exiting program.")
        sys.exit(0)


if __name__ == "__main__":
    main()
