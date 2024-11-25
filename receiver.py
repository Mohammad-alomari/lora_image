import RPi.GPIO as GPIO
from lora_e220 import LoRaE220, print_configuration, ResponseStatusCode, Configuration
import serial
import time
import base64
from io import BytesIO
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
CHUNK_SIZE = 128  # Bytes per chunk (can be adjusted)
ACK_TIMEOUT = 2  # Timeout in seconds to wait for ACK
MAX_RETRIES = 5  # Max retries per chunk

# OUTPUT_IMAGE = "received_image.jpg"

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

def calculate_checksum(data):
    """Calculate checksum for the given data."""
    try:
        return sum(data) % 256
    except Exception as e:
        print(f"Error calculating checksum: {e}")
        return None

def wait_for_chunk(lora):
    """
    Wait for a chunk from the sender.
    Returns a tuple: (chunk_data, is_eof)
    """
    while True:
        if lora.available() > 0:
            code, received_message = lora.receive_message()
            if code != ResponseStatusCode.SUCCESS:
                print(f"Error receiving message: {ResponseStatusCode.get_description(code)}")
                continue
            
            # Ensure message is bytes, not string
            message = received_message  
            print(f"Received message: {message}")

            # Check for End-of-File (EOF)
            if message.strip() == "EOF":
                return None, True
            
            return f"{message}", False
        time.sleep(0.1)

def process_chunk(chunk):
    """
    Process a single received chunk.
    Returns a tuple: (is_valid, chunk_id)
    """
    try:
        # Split the chunk into parts
        parts = chunk.split("|", 3)  
        chunk_id = parts[0]
        total_chunks = parts[1]
        checksum = int(parts[2])
        data = parts[3]  

        # Verify checksum
        if calculate_checksum(data.encode('utf-8')) != checksum:
            print(f"Checksum mismatch for chunk {chunk_id}")
            return False, chunk_id
        
        return True, (chunk_id, total_chunks, data)
    except Exception as e:
        print(f"Error processing chunk: {e}")
        return False, None

def acknowledge_chunk(lora, chunk_id, success):
    """
    Send acknowledgment for the received chunk.
    """
    ack = f"ACK|{chunk_id}" if success else f"ERR|{chunk_id}"
    lora.send_transparent_message(ack)  # Ensure we send a byte string
    print(f"Sent {'ACK' if success else 'ERR'} for chunk {chunk_id}")

def receive_image(lora):
    """
    Main function to receive an image over LoRa.
    """
    received_chunks = {}
    total_chunks = None

    print("Waiting for image...")
    while True:
        chunk, is_eof = wait_for_chunk(lora)
        if is_eof:
            print("EOF received. Image transfer complete.")
            break

        success, result = process_chunk(chunk)
        if success:
            chunk_id, total_chunks, data = result
            received_chunks[int(chunk_id)] = data
            acknowledge_chunk(lora, chunk_id, True)
        else:
            chunk_id = result
            acknowledge_chunk(lora, chunk_id, False)
    base64_string = ""
    # Assemble the received chunks into the image
    if total_chunks is not None and len(received_chunks) == int(total_chunks):
        for i in range(0, int(total_chunks)):
            if i in received_chunks:
                base64_string += received_chunks[i]
            else:
                print(f"Missing chunk {i}. Image assembly incomplete.")
        else:
            image_data = base64.b64decode(base64_string)
            image = Image.open(BytesIO(image_data))
            image.save("output_image.png")
            print(f"Image saved to output_image.png")
    else:
        print(f"Failed to receive all chunks. Received {len(received_chunks)} out of {total_chunks}.")

def main():
    lora = init_lora()
    try:
        receive_image(lora)
    except KeyboardInterrupt:
        print("Receiver interrupted. Exiting.")
    finally:
        print("finished")

if __name__ == "__main__":
    main()