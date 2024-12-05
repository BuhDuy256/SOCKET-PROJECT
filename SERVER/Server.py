import os
import re
import time
import struct
import socket
import threading

HEADER_SIZE = 64
PORT_NUMBER = 5050
SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_ADDRESS = (SERVER_IP, PORT_NUMBER)
FORMAT = 'utf-8'
CONNECT_MESSAGE = "!CONNECT"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_NAME = "allow_download.txt"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(SERVER_ADDRESS)

def send_file(connection, file_path):
    print(f"[SENDING FILE] Sending file to client {connection.getpeername()}...")

    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        print(f"[ERROR] File {file_path} not found!")
        send_message(connection, f"ERROR: File '{file_path}' not found.")
        return
    except Exception as e:
        print(f"[ERROR] Error reading file: {e}")
        send_message(connection, f"ERROR: {str(e)}")
        return

    file_name = os.path.basename(file_path).encode()
    data_length = len(data)

    header = struct.pack("!B H I", 0x01, len(file_name), data_length)
    header += file_name

    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        connection.sendall(header)
        connection.sendall(data)
        print("[INFO] File sent successfully!")
    except Exception as e:
        print(f"[ERROR] Error sending file: {e}")
        send_message(connection, f"ERROR: {str(e)}")

def send_message(connection, message):
    print(f"[SENDING MESSAGE] Sending message to client {connection.getpeername()}...")

    message_bytes = message.encode()
    data_length = len(message_bytes)

    header = struct.pack("!B I", 0x02, data_length)
    
    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        connection.sendall(header)
        connection.sendall(message_bytes)
        print("[INFO] Message sent successfully!")
    except Exception as e:
        print(f"[ERROR] Error sending message: {e}")

def handle_client(connection, addr):
    print(f"[NEW CONNECTION] {addr} connected.")

    connected = True
    while connected:
        header = connection.recv(HEADER_SIZE)
        if not header:
            break
        header_type = header[0]
        
        if header_type == 0x01:
            filename_length, data_length = struct.unpack("!H I", header[1:7])
            filename = header[7:7 + filename_length].decode()
            print(f"[FILE RECEIVED] Filename: {filename}")
            
            remaining_data = data_length
            file_data = b""
            
            while remaining_data > 0:
                chunk = connection.recv(min(remaining_data, 4096))
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

        elif header_type == 0x02:
            data_length = struct.unpack("!I", header[1:5])[0]
            
            message = connection.recv(data_length).decode()
            print(f"[{addr}] {message}")
            
            if message == CONNECT_MESSAGE:
                send_file(connection, FILE_NAME)
            elif message == DISCONNECT_MESSAGE:
                connected = False
            elif message.startswith("DOWNLOAD"):
                match = re.match(r"^DOWNLOAD (\S+) (\d+) (\d+)$", message)
                if match:
                    file_name = match.group(1)
                    offset = int(match.group(2))
                    chunk_size = int(match.group(3))

                    send_message(connection, f"OK!")
                else:
                    send_message(connection, "ERROR: Invalid DOWNLOAD command format.")
            else:
                send_message(connection, "ERROR: Invalid command.")
                connected = False
        else:
            send_message(connection, "ERROR: Unknown header type.")
            connected = False

    connection.close()

def multithread_start():
    server.listen()
    print(f"[LISTENING]: Server is listening on {SERVER_IP}")
    
    while True:
        connection, addr = server.accept()
        thread = threading.Thread(target = handle_client, args = (connection, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS]: {threading.active_count() - 1}")

multithread_start()
