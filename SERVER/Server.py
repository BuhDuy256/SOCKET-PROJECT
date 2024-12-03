import socket
import threading

HEADER = 64
PORT = 5050
SERVER = socket.gethostbyname(socket.gethostname())
ADDRESS = (SERVER, PORT)
FORMAT = 'utf-8'
START_MESSAGE = "BUHDUY"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_NAME = "allow_download.txt"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDRESS)

def send(conn, msg):
    message = msg.encode(FORMAT)
    msg_length = len(message)
    send_length = str(msg_length).encode(FORMAT)
    send_length += b' ' * (HEADER - len(send_length))
    conn.send(send_length)
    conn.send(message)
    
def send_allow_dowload_file(conn, filename):
    try:
        with open(filename, 'rb') as file:
            file_data = file.read()
            file_size = len(file_data)
            send(conn, str(file_size))
            conn.send(file_data)
            print(f"Sent {filename} to client.")
    except Exception as e:
        print(f"Error sending file: {e}")
        send(conn, "ERROR: Could not send file.")

def handle_client(conn, addr):
    print(f"\n[NEW CONNECTION]: {addr} connected.")
    connected = True
    while connected:
        msg_length = conn.recv(HEADER).decode(FORMAT)
        if msg_length:
            msg_length = int(msg_length)
            msg = conn.recv(msg_length).decode(FORMAT)

            if msg == START_MESSAGE:
                send_allow_dowload_file(conn, FILE_NAME)
                send(conn, "READY TO RECEIVE FILE")
                continue
            elif msg == DISCONNECT_MESSAGE:
                print(f"[DISCONNECTED]: {addr} disconnected.")
                connected = False
                return
            else:
                print(f"Received message from {addr}: {msg}")
                response = input("Reply: ")
                send(conn, response)
    conn.close()

def start():
    server.listen()
    print(f"[LISTENING] on {SERVER}")
    while True:
        print("[WAITING]")
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[NUMBER OF CONNECTION]: {threading.active_count() - 1}")

start()
