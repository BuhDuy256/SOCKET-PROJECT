import socket
import os
import hashlib

def calculate_checksum(data):
    """
    Tính giá trị băm SHA-256 cho dữ liệu.
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(data)
    return hash_obj.hexdigest()

def handle_client(client_socket, file_path):
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
                    chunk_size = min(1024, end - start)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    
                    # Tính giá trị CHECKSUM
                    checksum = calculate_checksum(data)
                    
                    # Gửi dữ liệu và CHECKSUM
                    client_socket.send(data)
                    client_socket.send(checksum.encode())
                    start += len(data)
    except Exception as e:
        print(f"Lỗi server: {e}")
    finally:
        client_socket.close()

def main():
    server_ip = socket.gethostbyname(socket.gethostname())
    server_port = 5000
    file_path = "5MB.zip"

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((server_ip, server_port))
    server_socket.listen(5)
    print(f"Server đang chạy tại {server_ip}:{server_port}...")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Kết nối từ {addr}")
        handle_client(client_socket, file_path)

if __name__ == "__main__":
    main()
