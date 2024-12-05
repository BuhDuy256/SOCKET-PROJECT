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
    with open(file_path, "rb") as f:
        data = f.read()

    file_name = file_path.encode()
    data_length = len(data)

    # Header: [type (1 byte), filename length (2 bytes), data length (4 bytes), filename (remaining)]
    # The string "!B H I" is a format string used by Python's struct module to define how binary data is packed or unpacked.
    header = struct.pack("!B H I", 0x01, len(file_name), data_length)
    header += file_name  # Add the filename (variable length)
    padding = b'\x00' * (HEADER_SIZE - len(header))  # Add padding to make header 64 bytes
    header += padding

    # Send header and data
    connection.sendall(header)
    connection.sendall(data)

def send_message(connection, message):
    message_bytes = message.encode()
    data_length = len(message_bytes)

    # Header: [type (1 byte), data length (4 bytes), padding]
    header = struct.pack("!B I", 0x02, data_length)
    header += b'\x00' * (HEADER_SIZE - len(header))

    # Send header and data
    connection.sendall(header)
    connection.sendall(message_bytes)

def handle_client(connection, addr):
    print(f"[NEW CONNECTION] {addr} connected.")

    connected = True
    while connected:
        # Read header
        header = connection.recv(HEADER_SIZE)
        if not header:
            break
        # Unpack header
        header_type, filename_length, data_length = struct.unpack("!B H I", header[:7])

        if header_type == 0x01:
            # Read filename
            filename = connection.recv(filename_length).decode()
            # Read data
            data = connection.recv(data_length)
            # Write data to file
            with open(filename, "wb") as f:
                f.write(data)
            print(f"[{addr}] File '{filename}' received.")

        elif header_type == 0x02:
            # Read data
            message = connection.recv(data_length).decode()
            print(f"[{addr}] {message}")
            # Check message
            if message == CONNECT_MESSAGE:
                send_file(connection, FILE_NAME)
            elif message == DISCONNECT_MESSAGE:
                connected = False
            elif message.startswith("DOWNLOAD"):
                # Check if the message matches the format using regex
                match = re.match(r"^DOWNLOAD (\S+) (\d+) (\d+)$", message)
                if match:
                    file_name = match.group(1)  # Extract the filename
                    offset = int(match.group(2))  # Extract the offset
                    chunk_size = int(match.group(3))  # Extract the chunk size

                    print(f"[{addr}] DOWNLOAD request received: file={file_name}, offset={offset}, chunk_size={chunk_size}")

                #     try:
                #         # ... code to send the requested file chunk ...
                #     except FileNotFoundError:
                #         send_message(connection, f"ERROR: File '{file_name}' not found.")
                #     except ValueError:
                #         send_message(connection, "ERROR: Invalid offset or chunk size.")
                #     except Exception as e:
                #         send_message(connection, f"ERROR: {str(e)}")
                # else:
                #     send_message(connection, "ERROR: Invalid DOWNLOAD command format.")
            else:
                send_message(connection, "ERROR: Invalid command.")
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
