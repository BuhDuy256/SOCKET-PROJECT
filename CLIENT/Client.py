import os
import re
import time
import tqdm
import socket
import threading
import hashlib

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 5050
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64 # 64 bytes
CHECKSUM_SIZE = 16 # 16 bytes

DISCONNECT_MESSAGE = '!DISCONNECT'

BUFFER_SIZE = 1024

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(SERVER_ADDRESS)

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
	
def receive_downloaded_file_list():
    file_list = []
    message = receive_message(client)

    if message:
        file_lines = message.strip().split("\n")
        for file_line in file_lines:
            file_line = file_line.strip()

            file_info = file_line.split(" ")

            if len(file_info) >= 2:
                file_name = file_info[0]
                file_size = " ".join(file_info[1:3])
                size_value, size_unit = file_size.split()

                file_list.append({
                    "file_name": file_name,
                    "size_value": size_value,
                    "size_unit": size_unit
                })

    return file_list


def display_file_list(file_list):
    if not file_list:
        print("No files available to download.")
        return

    for file in file_list:
        print(f"{file['file_name']} {file['size_value']}{file['size_unit']}")
        
if __name__ == "__main__":
    file_list = receive_downloaded_file_list()

    display_file_list(file_list)

    send_message(client, DISCONNECT_MESSAGE)
    client.close()
