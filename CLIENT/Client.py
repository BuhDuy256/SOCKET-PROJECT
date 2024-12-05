import os
import struct
import socket
import threading

HEADER_SIZE = 64
PORT_NUMBER = 5050
SERVER_IP = "172.20.10.2"
SERVER_ADDRESS = (SERVER_IP, PORT_NUMBER)
FORMAT = 'utf-8'
CONNECT_MESSAGE = "!CONNECT"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_REQUESTED_DOWNLOAD_PATH = "input.txt"

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

def handle_server():
    header = client.recv(HEADER_SIZE)
    if not header:
        print("[ERROR] No header received. Closing connection.")
        client.close()
        return

    header_type = header[0]
    
    if header_type == 0x01:
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
            print(f"[FILE DATA]\n{decoded_content}")
        else:
            print("[ERROR] No data received for the file.")

    elif header_type == 0x02:
        data_length = struct.unpack("!I", header[1:5])[0]
        
        message = client.recv(data_length).decode()
        print(f"[SERVER] {message}")
    else:
        send_message("ERROR: Unknown header type.")

send_message(CONNECT_MESSAGE)
handle_server()
send_message(DISCONNECT_MESSAGE)
