import os
import re
import time
import struct
import socket
import threading
import hashlib

HEADER_SIZE = 64
PORT_NUMBER = 5050
SERVER_IP = "192.168.100.8"
SERVER_ADDRESS = (SERVER_IP, PORT_NUMBER)
FORMAT = 'utf-8'
CONNECT_MESSAGE = "!CONNECT"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_REQUESTED_DOWNLOAD_PATH = "input.txt"
CHECKSUM_SIZE = 16
NUM_THREADS = 4

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(SERVER_ADDRESS)


def receive_file_chunk(header, chunk_name):
    file_path_len, offset, chunk_size = struct.unpack("!H I I", header[1:11])
    
    file_path = header[11:11 + file_path_len].decode(FORMAT)
    checksum = header[11 + file_path_len: 11 + file_path_len + CHECKSUM_SIZE]

    chunk_data = client.recv(chunk_size)
    if not chunk_data:
        print(f"[ERROR] No data received for chunk.")
        return

    received_checksum = hashlib.md5(chunk_data).digest()

    if received_checksum != checksum:
        print(f"[ERROR] Checksum mismatch. Expected {checksum.hex()} but got {received_checksum.hex()}.")
        send_message(f"ERROR: Checksum mismatch for chunk.")
        return

    try:
        with open(chunk_name, "wb") as f:
            f.write(chunk_data)

        print(f"[INFO] Successfully wrote chunk to {chunk_name}.")
        
    except Exception as e:
        print(f"[ERROR] Error writing chunk to file: {e}")
        send_message(f"ERROR: {str(e)}")

def handle_server(chunk_name ="test_chunk.zip"):
    header = client.recv(HEADER_SIZE)
    if not header:
        print("[ERROR] No header received. Closing connection.")
        client.close()
        return

    header_type = header[0]
    
    if header_type == 0x01:
        receive_file(header)

    elif header_type == 0x02:
        message = receive_message(header)
        print(f"[MESSAGE RECEIVED] {message}")

    elif header_type == 0x03:
        receive_file_chunk(header, chunk_name)

    else:
        send_message("ERROR: Unknown header type.")



def scan_input(file_path):
    '''Scan the input file per 5 seconds and return the list lines'''
    lines = []
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[ERROR] File '{file_path}' not found.")
    except Exception as e:
        print(f"[ERROR] {str(e)}")
    return lines

def format_file_size(file_size):

    ''' 
    Input: string
    Output: float
    Convert 100 MB -> 100
    Convert 1GB -> 1024
    '''
    size = float(file_size[:-2])
    if file_size[-2:] == "MB":
        size *= 1024
    
    return int(size)


def download_file(file_name, file_size):
    ''' Create 4 theads to download the a quarter of the file'''

    thread_list = []
    chunk_names = [f"{file_name}.part{i}" for i in range(NUM_THREADS)]
    for i in range(NUM_THREADS):
        thread = threading.Thread(target=download_chunk, args=(file_name, file_size, i, chunk_names[i]))
        thread_list.append(thread)
        thread.start()
    
    # Wait for all threads to finish
    for thread in thread_list:
        thread.join()

    # Merge the chunks
    


def download_chunk(file_name, file_size, chunk_num, chunk_name):
    send_message(CONNECT_MESSAGE)
    handle_server()
    offset = chunk_num * file_size // NUM_THREADS
    chunk_size = file_size // NUM_THREADS
    if chunk_num == NUM_THREADS - 1:
        chunk_size += file_size % NUM_THREADS
    send_message(f"DOWNLOAD {file_name} {offset} {chunk_size}")
    handle_server(chunk_name)
    print(f"[INFO] Chunk {chunk_name} downloaded.")

def merge_files(output_file, chunks):
    """
    Merges all the downloaded chunks into the final file.

    Args:
        output_file (str): The name of the final output file.
        chunks (list): List of chunk file names to merge.
    """
    try:
        with open(output_file, "wb") as merged_file:
            for chunk_file in sorted(chunks):
                if not os.path.exists(chunk_file):
                    print(f"[ERROR] Missing chunk: {chunk_file}")
                    continue

                with open(chunk_file, "rb") as chunk:
                    merged_file.write(chunk.read())
                os.remove(chunk_file)  # Delete chunk after merging
                print(f"[INFO] Merged {chunk_file} into {output_file}")
        print(f"[SUCCESS] File {output_file} assembled successfully!")
    except Exception as e:
        print(f"[ERROR] Error during merging: {e}")
    




def main():
    request_file = []

    request_file = scan_input(FILE_REQUESTED_DOWNLOAD_PATH)
    for line in request_file:
        file_name, file_size = line.split()
        download_file(file_name, format_file_size(file_size))

        time.sleep(5)

if __name__ == "__main__":
    main()
        

