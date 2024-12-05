import os
import re
import time
import struct
import socket
import threading
import hashlib

HEADER_SIZE = 64
PORT_NUMBER = 5050
SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_ADDRESS = (SERVER_IP, PORT_NUMBER)
FORMAT = 'utf-8'
CONNECT_MESSAGE = "!CONNECT"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_NAME = "allow_download.txt"
CHECKSUM_SIZE = 16

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

    file_path_bytes = os.path.basename(file_path).encode(FORMAT)
    data_length = len(data)

    # Header: [type (1 byte), filename length (2 bytes), data length (4 bytes), file name bytes (variable), padding]
    header = struct.pack("!B H I", 0x01, len(file_path_bytes), data_length)
    header += file_path_bytes

    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        connection.sendall(header)
        connection.sendall(data)
        print("[INFO] File sent successfully!")
    except Exception as e:
        print(f"[ERROR] Error sending file: {e}")
        send_message(connection, f"ERROR: {str(e)}")

def receive_file(connection, header):
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

def send_message(connection, message):
    print(f"[SENDING MESSAGE] Sending message to client {connection.getpeername()}...")

    message_bytes = message.encode()
    data_length = len(message_bytes)

    # Header: [type (1 byte), data length (4 bytes), padding]
    header = struct.pack("!B I", 0x02, data_length)
    
    padding = b'\x00' * (HEADER_SIZE - len(header))
    header += padding

    try:
        connection.sendall(header)
        connection.sendall(message_bytes)
        print("[INFO] Message sent successfully!")
    except Exception as e:
        print(f"[ERROR] Error sending message: {e}")

def receive_message(connection, header):
    data_length = struct.unpack("!I", header[1:5])[0]
    message = connection.recv(data_length).decode(FORMAT)
    return message

def send_chunk_file(connection, file_path, offset, chunk_size):
    try:
        with open(file_path, "rb") as f:
            f.seek(offset)
            file_chunk = f.read(chunk_size)
            
            if not file_chunk:
                send_message(connection, "ERROR: No data to send.")
                return

            checksum = hashlib.md5(file_chunk).digest()

            file_path_bytes = file_path.encode('utf-8')
            file_path_len = len(file_path_bytes)

            # Header: [type (1 byte), filename length (2 bytes), offset (4 bytes), chunk size (4 bytes), file name bytes (variable), checksum (16 bytes), padding]
            header = struct.pack(
                "!B H I I",
                0x03,           
                file_path_len,   
                offset,          
                chunk_size
            )
            
            header += file_path_bytes
            header += checksum

            padding = b'\x00' * (HEADER_SIZE - len(header))
            header += padding

            connection.sendall(header)
            connection.sendall(file_chunk)

            print(f"[INFO] Sent chunk of size {len(file_chunk)} from offset {offset}.")
    
    except FileNotFoundError:
        print(f"[ERROR] File '{file_path}' not found!")
        send_message(connection, f"ERROR: File '{file_path}' not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")
        send_message(connection, f"ERROR: {str(e)}")

def handle_client(connection, addr):
    print(f"[NEW CONNECTION] {addr} connected.")

    connected = True
    while connected:
        header = connection.recv(HEADER_SIZE)
        if not header:
            break
        header_type = header[0]
        
        if header_type == 0x01:
            receive_file(connection, header)

        elif header_type == 0x02:
            message = receive_message(connection, header)
            
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

                    send_chunk_file(connection, file_name, offset, chunk_size)

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
