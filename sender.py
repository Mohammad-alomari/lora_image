import RPi.GPIO as GPIO
from lora_e220 import LoRaE220, print_configuration, ResponseStatusCode, Configuration
import serial
import time
import base64
from PIL import Image

# GPIO setup
GPIO.setwarnings(False)  # Suppress warnings
GPIO.setmode(GPIO.BCM)  # Use Broadcom pin numbering

# Pin configuration
AUX_PIN = 18
M0_PIN = 23
M1_PIN = 24

GPIO.setup(AUX_PIN, GPIO.IN)  # AUX pin is input
GPIO.setup(M0_PIN, GPIO.OUT)  # M0 pin is output
GPIO.setup(M1_PIN, GPIO.OUT)  # M1 pin is output

# Configuration
CHUNK_SIZE = 190 # Bytes per chunk (can be adjusted)
ACK_TIMEOUT = 2  # Timeout in seconds to wait for ACK
MAX_RETRIES = 5  # Max retries per chunk


# Set the LoRa module to Transmit Mode
# lora.set_mode('TRANSMIT') --> See docs?!

# Initialize LoRa
def init_lora():
    loraSerial = serial.Serial('/dev/serial0', baudrate=9600)
    lora = LoRaE220('900T30D', loraSerial, aux_pin=AUX_PIN, m0_pin=M0_PIN, m1_pin=M1_PIN)

    code = lora.begin()
    print("Initialization: {}", ResponseStatusCode.get_description(code))

    config_to_set = Configuration("900T30D")
    config_to_set.CHAN = 18
    code, confsetted = lora.set_configuration(config_to_set)
    print("Config set: {}", ResponseStatusCode.get_description(code))

    code, configuration = lora.get_configuration()
    print("Retrieve configuration: {}", ResponseStatusCode.get_description(code))
    print(configuration)
    print_configuration(configuration)
    return lora

# while True:
    # Send a test message
    # message = input("Send Message: ")
    # lora.send_transparent_message(message)  # Send the message
    # print(f"Sent: {message}")

# Read and encode the image in Base64
def read_and_encode_image(image_path):
    with open(image_path, "rb") as img_file:
        encoded = base64.b64encode(img_file.read())
    return encoded


# Split Base64 data into chunks
def split_data(data, chunk_size):
    chunks = []
    total_chunks = len(data) // chunk_size + (1 if len(data) % chunk_size else 0)
    for i in range(total_chunks):
        chunk_data = data[i * chunk_size:(i + 1) * chunk_size]
        checksum = sum(chunk_data) % 256
        chunks.append({
            "chunk_id": i,
            "total_chunks": total_chunks,
            "data": chunk_data,
            "checksum": checksum
        })
    return chunks


# Wait for acknowledgment from the receiver
def wait_for_ack(lora, expected_chunk_id):
    start_time = time.time()
    while time.time() - start_time < ACK_TIMEOUT:
        if lora.available():
            code, response = lora.receive_message()
            print(response)
            print(expected_chunk_id)
            if response == f"ACK|{expected_chunk_id}":
                return True
            elif response == f"ERROR:{expected_chunk_id}":
                return False
    return False


def send_image(lora, chunks):
    for chunk in chunks:
        success = False
        retries = 0

        while not success and retries < MAX_RETRIES:
            header = f"{chunk['chunk_id']}|{chunk['total_chunks']}|{chunk['checksum']}|"
            data = chunk["data"].decode("latin1") 
            payload = header + data  

            lora.send_transparent_message(payload) 
            print(f"Sent chunk {chunk['chunk_id']}...")

            if wait_for_ack(lora, chunk["chunk_id"]):
                success = True
                print(f"ACK received for chunk {chunk['chunk_id']}")
            else:
                retries += 1
                print(f"Retrying chunk {chunk['chunk_id']} ({retries}/{MAX_RETRIES})")

        if not success:
            print(f"Failed to send chunk {chunk['chunk_id']} after {MAX_RETRIES} retries.")
            return False

    lora.send_transparent_message("EOF") 
    print("End of File (EOF) sent.")
    return True

# scale image down
def resize_image(input_image_path, output_image_path, new_width=800, new_height=600):
    with Image.open(input_image_path) as img:
        resized_img = img.resize((new_width, new_height))

        resized_img.save(output_image_path)
        print(f"Resized image saved as {output_image_path}")


def main():
    lora = init_lora()
    resize_image("./Downloads/background.jpg", "resized_image.jpg", new_width=50, new_height=50)
    image_path = "./resized_image.jpg" 
    encoded_data = read_and_encode_image(image_path)
    chunks = split_data(encoded_data, CHUNK_SIZE)
    send_image(lora, chunks)

if __name__ == "__main__":
    main()
