import os
import re
import time
import socket
import threading
import hashlib

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 5050
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64  # 64 bytes
CHECKSUM_SIZE = 16  # 16 bytes

DISCONNECT_MESSAGE = '!DISCONNECT'

BUFFER_SIZE = 1024

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(SERVER_ADDRESS)


def convert_size(size_in_bytes):
    if size_in_bytes <= 0:
        return "0B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]

    i = 0
    while size_in_bytes >= 1024 and i < len(units) - 1:
        size_in_bytes /= 1024.0
        i += 1

    return f"{size_in_bytes:.2f} {units[i]}"


def send_downloaded_file_list(connection):
    server_dir = os.path.dirname(os.path.abspath(__file__))
    exclude_files = ['Server.py']

    files_in_directory = os.listdir(server_dir)
    files = [file for file in files_in_directory if os.path.isfile(os.path.join(server_dir, file)) and file not in exclude_files]

    file_list_str = []
    for file in files:
        file_size = os.path.getsize(os.path.join(server_dir, file))
        file_size_str = convert_size(file_size)
        file_list_str.append(f"{file} {file_size_str}")

    message = "\n".join(file_list_str)

    send_message(connection, message)


def send_message(connection, message):
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    connection.send(header)
    connection.send(message)


def receive_message(connection):
    header = connection.recv(HEADER_SIZE).decode(ENCODE_FORMAT)
    if not header:
        return None

    message = connection.recv(int(header)).decode(ENCODE_FORMAT)
    return message

def send_chunk_file(connection, file_name, offset, chunk_size):
    if not os.path.exists(file_name):
        send_message(connection, "SERVER RESPONSE::CHUNK FILE NOT FOUND")
        return

    send_message(connection, "SERVER RESPONSE::SENDING CHUNK FILE: " + file_name + " " + str(offset) + " " + str(chunk_size))


def handle_client(connection, address):
    print(f"Client connected: {address}")
    connected = True

    while connected:
        try:
            message = receive_message(connection)

            if message == DISCONNECT_MESSAGE:
                connected = False
                connection.close()
                print(f"Client {address} disconnected.")
                break

            elif message.startswith("DOWLOAD"):
                match = re.match(r"^DOWLOAD (\S+) (\d+) (\d+)$", message)

                if match:
                    file_name = match.group(1)
                    offset = int(match.group(2))
                    size = int(match.group(3))

                    send_chunk_file(connection, file_name, offset, size)

            else:
                send_message(connection, "Invalid Command")
                connected = False

        except (ConnectionResetError, BrokenPipeError):
            print(f"Client {address} disconnected unexpectedly.")
            connected = False

    connection.close()


def TCP_start():
    server.listen()

    while True:
        connection, address = server.accept()
        
        send_downloaded_file_list(connection)

        thread = threading.Thread(target=handle_client, args=(connection, address))
        thread.start()
        

if __name__ == "__main__":
    TCP_start()
