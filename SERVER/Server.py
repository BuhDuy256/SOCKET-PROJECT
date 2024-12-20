import socket
import os
import hashlib
import struct
import threading


MAX_WORKERS = 16  # Limit number of threads to prevent server from crashing
CHUNK_SIZE = 1024  # 1 KB
SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345

def calculate_checksum(data):
    """
    Tính giá trị băm SHA-256 cho dữ liệu.
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(data)
    return hash_obj.hexdigest()

def handle_client(client_socket):
    try:
        request = client_socket.recv(1024).decode()
        command, file_name, *args = request.strip().split()

        if command == "SIZE":
            # Trả về kích thước tệp
            file_size = os.path.getsize(file_name)
            client_socket.send(str(file_size).encode())
        
        elif command == "GET":
            start = int(args[0])
            end = int(args[1])
            with open(file_name, "rb") as f:
                f.seek(start)
                while start < end:
                    chunk_size = min(CHUNK_SIZE, end - start)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    
                    # Tính CHECKSUM cho chunk
                    checksum = calculate_checksum(data)
                    
                    # Đóng gói: [dữ liệu_length (4 byte)][dữ liệu][CHECKSUM (64 byte)]
                    packed_data = struct.pack(f"!I{len(data)}s64s", len(data), data, checksum.encode())
                    client_socket.sendall(packed_data)

                    start += len(data)

        elif command == "GET_CHUNK":
            chunk_start = int(args[0])
            chunk_size = int(args[1])
            with open(file_name, "rb") as f:
                f.seek(chunk_start)
                data = f.read(chunk_size)
                
                # Tính CHECKSUM
                checksum = calculate_checksum(data)
                
                # Đóng gói và gửi
                packed_data = struct.pack(f"!I{len(data)}s64s", len(data), data, checksum.encode())
                client_socket.send(packed_data)

    except Exception as e:
        print(f"Error in handle_client: {e}")
    finally:
        client_socket.close()


    

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((SERVER_IP, SERVER_PORT))
    server_socket.listen(5)
    print(f"Server is running on {SERVER_IP}:{SERVER_PORT}...")
    
    while True:
        connection, address = server_socket.accept()
        print(f"Connection from {address}")
        thread = threading.Thread(target=handle_client, args=(connection,))
        thread.start()

if __name__ == "__main__":
    main()
