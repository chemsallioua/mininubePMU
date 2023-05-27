import requests, json
import base64, struct, math, time

class RequestException(Exception):
    pass

class NodeGatewaySimulator:
    def __init__(self, url = "http://127.0.0.1:5000"):
        self.url = url

    def post_configure(self, configuration, endpoint = "/configure"):

        url = self.url + endpoint
        # Send the POST request with the configuration
        response = requests.post(url, json={"configuration": configuration})

        # Check the response
        if response.status_code == 200:
            # Successful response
            data = response.json()
            status = data["status"]
            print(f"Configuration status: {status}")
        else:
            # Error response
            raise RequestException(response.text)


    def get_estimate(self, data_frame, endpoint = "/estimate"):

        url = self.url + endpoint
        # Send the POST request with the data frame
        message= {"data_frame": data_frame}

        json_string = json.dumps(message)
        payload_size = len(json_string)
        print("Payload size:", payload_size, "bytes")

        response = requests.post(url, json=message)

        # Check the response
        if response.status_code == 200:
            return response.json()
        else:
            raise RequestException(response.text)

    @staticmethod
    def get_encoded_signal(nominal_freq = 50, amplitude = 1.0 ,phase = 0, frequency = 51.0, sampling_rate = 25600, n_cycles = 4):

        num_samples = n_cycles*sampling_rate//nominal_freq
        samples = []

        for i in range(num_samples):
            time = i / sampling_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * time + phase)
            samples.append(sample)

        # Convert the samples to a bytes object using double precision
        byte_data = b"".join(struct.pack("d", sample) for sample in samples)

        # Encode the bytes data to base64
        return base64.b64encode(byte_data).decode("utf-8")


if __name__ == "__main__":

    # Create a NodeGatewaySimulator object
    node_gateway = NodeGatewaySimulator(url = "http://16.16.255.226:8080")

    n_cycles = 4
    sample_rate = 51200//16
    nominal_freq = 50
    NUM_CHANNELS = 1

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
    try:
        node_gateway.post_configure(configuration)
    except Exception as e:   
        print(e)
    
    data_frame = {
        "timestamp":
            {
            "SOC": 123456789,
            "FRACSEC": 0,
            "timebase": 1000000
            },
    }

    # Add the encoded signal to the data frame
    data_frame["channels"] = []
    
    for i in range(1, NUM_CHANNELS+1):
        # Get the encoded signal
        signal_frequency = 50.0 + i
        encoded_signal = node_gateway.get_encoded_signal(nominal_freq = nominal_freq, frequency = signal_frequency, sampling_rate = sample_rate, n_cycles = n_cycles)

        data_frame["channels"].append({
            "channel_number": i,
            "payload": encoded_signal
        })

    # Get the estimate
    try:
        iterations = 4
        start = time.time()

        for i in range(0, iterations):
            estimate = node_gateway.get_estimate(data_frame)

        end = time.time()
        time_per_iter = (end - start)/iterations
        print("Frame rate:", 1/time_per_iter, " fps")
        print("Time:", time_per_iter*1000, " ms")
        print(estimate)
    except Exception as e:
        print(e)
    
    

    