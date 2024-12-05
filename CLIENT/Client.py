import os
import re
import time
import struct
import socket
import threading
import hashlib

HEADER_SIZE = 64
PORT_NUMBER = 5050
SERVER_IP = "172.20.10.2"
SERVER_ADDRESS = (SERVER_IP, PORT_NUMBER)
FORMAT = 'utf-8'
CONNECT_MESSAGE = "!CONNECT"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_REQUESTED_DOWNLOAD_PATH = "input.txt"
CHECKSUM_SIZE = 16

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(SERVER_ADDRESS)

def send_file(file_path):
    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        send_message(f"ERROR: File '{file_path}' not found.")
        return
    except Exception as e:
        send_message(f"ERROR: {str(e)}")
        return

    file_name = os.path.basename(file_path).encode()
    data_length = len(data)

    header = struct.pack("!B H I", 0x01, len(file_name), data_length)
    header += file_name

    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        client.sendall(header)
        client.sendall(data)
    except Exception as e:
        send_message(f"ERROR: {str(e)}")

def receive_file(header):
    filename_length, data_length = struct.unpack("!H I", header[1:7])
    filename = header[7:7 + filename_length].decode()
    
    remaining_data = data_length
    file_data = b""
    
    while remaining_data > 0:
        chunk = client.recv(min(remaining_data, 4096))
        if not chunk:
            break
        file_data += chunk
        remaining_data -= len(chunk)
    
        if file_data:
            print(f"[FILE RECEIVED] Filename: {filename}")
            decoded_content = file_data.decode(FORMAT)
            print(f"[FILE DATA]\n {decoded_content}")
        else:
            print("[ERROR] No data received for the file.")

def send_message(message):
    message_bytes = message.encode()
    data_length = len(message_bytes)

    header = struct.pack("!B I", 0x02, data_length)
    
    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        client.sendall(header)
        client.sendall(message_bytes)
    except Exception as e:
        print(f"[ERROR] Error sending message: {e}")

def receive_message(header):
    data_length = struct.unpack("!I", header[1:5])[0]
    message = client.recv(data_length).decode(FORMAT)
    return message

def receive_file_chunk(header):
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
        with open("test.txt", "r+b") as f:
            f.seek(offset)
            f.write(chunk_data)

        print(f"[INFO] Successfully wrote chunk to {file_path} at offset {offset}.")
        
    except Exception as e:
        print(f"[ERROR] Error writing chunk to file: {e}")
        send_message(f"ERROR: {str(e)}")

def handle_server():
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
        receive_file_chunk(header)

    else:
        send_message("ERROR: Unknown header type.")

send_message(CONNECT_MESSAGE)
handle_server()
send_message("DOWNLOAD 5MB.zip 0 1024")
handle_server()
send_message(DISCONNECT_MESSAGE)
