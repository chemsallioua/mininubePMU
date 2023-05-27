import asyncio
import websockets
import json
import time
import base64
import struct
import math

class WebsocketGatewaySimulator:
    def __init__(self, url="wss://pp06w1fdrj.execute-api.eu-north-1.amazonaws.com/dev"):
        self.url = url

    async def connect(self):
        self.websocket = await websockets.connect(self.url)

    async def send(self, action, payload):
        if action == "configure":
            payloadtype = "configuration"
        elif action == "estimate":
            payloadtype = "data_frame"
        else:
            raise ValueError("Unknown action")

        message = json.dumps({
            "action": action,
            payloadtype: payload
        })

        message_bytes = message.encode('utf-8')  # encode the string as bytes
        print("size of message: " ,len(message_bytes))  # print the size in bytes

        start = time.time()
        await self.websocket.send(message)
        response = await self.websocket.recv()
        end = time.time()
        elapsed_time = end - start

        return elapsed_time, response

    async def close(self):
        await self.websocket.close()

    @staticmethod
    def get_encoded_signal(nominal_freq=50, amplitude=1.0, phase=0, frequency=51.0, sampling_rate=25600, n_cycles=4):
        num_samples = n_cycles * sampling_rate // nominal_freq
        samples = []

        for i in range(num_samples):
            t = i / sampling_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * t + phase)
            samples.append(sample)

        # Convert the samples to a bytes object using double precision
        byte_data = b"".join(struct.pack("d", sample) for sample in samples)

        # Encode the bytes data to base64
        return base64.b64encode(byte_data).decode("utf-8")


async def main():
    # Create the simulator
    simulator = WebsocketGatewaySimulator(url="wss://pp06w1fdrj.execute-api.eu-north-1.amazonaws.com/dev")

    n_cycles = 4
    sample_rate = 51200//4
    nominal_freq = 50
    NUM_CHANNELS = 4

    # Connect to WebSocket
    await simulator.connect()

    # Configure PMU
    configuration = {
        "signal": {
            "n_cycles": n_cycles,
            "sample_rate": sample_rate,
            "nominal_freq": nominal_freq
        },
        "synchrophasor": {
            "frame_rate": 50,
            "number_of_dft_bins": 11,
            "ipdft_iterations": 3,
            "iter_e_ipdft_enable": 1,
            "iter_e_ipdft_iterations": 10,
            "interference_threshold": 0.0033
        },
        "rocof": {
            "threshold_1": 3,
            "threshold_2": 25,
            "threshold_3": 0.035,
            "low_pass_filter_1": 0.5913,
            "low_pass_filter_2": 0.2043,
            "low_pass_filter_3": 0.2043
        }
    }

    # Send the configuration
    await simulator.send("configure", configuration)

    # Create the data frame
    data_frame = {
        "timestamp": {
            "SOC": 123456789,
            "FRACSEC": 0,
            "timebase": 1000000
        },
    }

    data_frame["channels"] = []

    # Send the data
    for i in range(1, NUM_CHANNELS + 1):
        # Get the encoded signal
        signal_frequency = 50.0 + i
        encoded_signal = simulator.get_encoded_signal(nominal_freq=nominal_freq, frequency=signal_frequency,
                                                      sampling_rate=sample_rate, n_cycles=n_cycles)

        data_frame["channels"].append({
            "channel_number": i,
            "payload": encoded_signal
        })

    # Send the data frame to get the estimate
    try:
        iterations = 4
        start = time.time()

        for i in range(iterations):
            elapsed_time, estimate = await simulator.send("estimate", data_frame)
            print(f"Time: {elapsed_time * 1000} ms\n\n")
            # print(estimate)

        end = time.time()
        time_per_iter = (end - start) / iterations
        print(f"Frame rate: {1 / time_per_iter} fps")
        print(f"Average time per iteration: {time_per_iter * 1000} ms")
        # print(estimate)
    except Exception as e:
        print(e)

    # Close the WebSocket connection
    await simulator.close()


if __name__ == "__main__":
    asyncio.run(main())
