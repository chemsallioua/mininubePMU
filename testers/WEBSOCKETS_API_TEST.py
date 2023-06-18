import asyncio
import websockets
import json
import time
import base64
import struct
import math
import threading
from pythonping import ping
import speedtest
import csv
import statistics

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
        # print("size of message: " ,len(message_bytes))  # print the size in bytes

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

class CBPMUPerformanceEvaluation:
    def __init__(self, filename):
        self.filename = filename
        self.measurements = []

    async def main(self, thread_num, iter, channel_per_thread):
        # Create the simulator
        simulator = WebsocketGatewaySimulator(url="wss://pp06w1fdrj.execute-api.eu-north-1.amazonaws.com/dev")

        n_cycles = 4
        sample_rate = 51200//4
        nominal_freq = 50
        NUM_CHANNELS = channel_per_thread

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
            iterations = iter
            start = time.time()

            for i in range(iterations):
                elapsed_time, estimate = await simulator.send("estimate", data_frame)
                self.measurements.append((thread_num, i+1, elapsed_time * 1000, estimate))
                print(f"[Thread: {thread_num}] Time: {elapsed_time * 1000} ms")
                # print("[Thread: ", thread_num, "]: ", estimate)

            end = time.time()
            time_per_iter = (end - start) / iterations
            print(f"[Thread: {thread_num}] Frame rate: {1 / time_per_iter} fps")
            print(f"[Thread: {thread_num}] Average time per iteration: {time_per_iter * 1000} ms")
            # print(estimate)
        except Exception as e:
            print(e)

        # Close the WebSocket connection
        await simulator.close()

    def run_main(self,thread_num, iter=100, channel_per_thread=4):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.main(thread_num, iter, channel_per_thread))
        loop.close()
    
    def save_to_csv(self):
        header_exists = False
        try:
            with open(self.filename, "r", newline="") as csvfile:
                reader = csv.reader(csvfile)
                header = next(reader, [])
                if header == ["Thread", "Iteration", "Time", "Estimate"]:
                    header_exists = True
        except FileNotFoundError:
            pass

        with open(self.filename, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if not header_exists:
                writer.writerow(["Thread", "Iteration", "Time", "Estimate"])
            for result in self.measurements:
                writer.writerow(result)

        print(f"Output saved to {self.filename}")

    def print_get_statistics(self):
        times = [result[2] for result in self.measurements]

        max_time = max(times)
        min_time = min(times)
        mean = statistics.mean(times)
        median = statistics.median(times)
        std_deviation = statistics.stdev(times)

        print("\n------Time per request------")

        print(f"Min: {min_time} ms")
        print(f"Max: {max_time} ms")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard Deviation: {std_deviation} ms")

        max_fps = 1000 / min_time
        min_fps = 1000 / max_time
        mean_fps = 1000 / mean
        median_fps = 1000 / median
        std_deviation_fps = 1000 / std_deviation

        print("\n------Frame Rate------")

        print(f"Min FPS: {min_fps}")
        print(f"Max FPS: {max_fps}")
        print(f"Mean FPS: {mean_fps}")
        print(f"Median FPS: {median_fps}")
        print(f"Standard Deviation FPS: {std_deviation_fps}")


        return max_time, min_time, mean, median, std_deviation, max_fps, min_fps, mean_fps, median_fps, std_deviation_fps

@staticmethod
def measure_latency(host):
    response_list = ping(host, count=100)  # Send 10 ping requests
    avg_latency = response_list.rtt_avg_ms
    return avg_latency

@staticmethod
def measure_bandwidth():
    st = speedtest.Speedtest(secure=True)
    # best_server = st.get_best_server()
    download_speed = st.download() / 1_000_000  # in Mbps
    upload_speed = st.upload() / 1_000_000  # in Mbps
    return download_speed, upload_speed

if __name__ == "__main__":

    
    iterations = 500  # Number of iterations per thread
    host = "ec2-13-53-234-92.eu-north-1.compute.amazonaws.com"

    filename_stats = f"summary_stats.csv"

    with open(filename_stats, "w", newline="") as csvfile:

        writer = csv.writer(csvfile)
        writer.writerow(["Number of Threads", "Number of Channels", "Ping Latency", "Download speed", "Upload speed",
                            "Max Time", "Min Time", "Mean", "Median", "Standard Deviation",
                            "Max FPS", "Min FPS", "Mean FPS", "Median FPS", "Standard Deviation FPS"])

        for num_of_threads in [10, 50, 100]:
            for channel_per_thread in [1,2,3,4]:

                print("\n#################################################################################################")
                print(f"\n\n\ NEW TEST  -  Threads: {num_of_threads}  Channels per thread: {channel_per_thread}  Iterations: {iterations} \n\n")

                filename_measurments = f"measurements_t{num_of_threads}_ch{channel_per_thread}.csv"

                cb_pmu = CBPMUPerformanceEvaluation(filename_measurments)
                avg_latency = measure_latency(host)
                print("\n===========================================================================")
                print(f"Average latency: {avg_latency} ms")

                download_speed, upload_speed = measure_bandwidth()
                print(f"Download speed: {download_speed} Mbps")
                print(f"Upload speed: {upload_speed} Mbps")
                print("\n===========================================================================")

                threads = []
                for i in range(num_of_threads):
                    thread = threading.Thread(target=cb_pmu.run_main, args=(i,iterations, channel_per_thread))
                    threads.append(thread)
                    thread.start()

                for thread in threads:
                    thread.join()

                cb_pmu.save_to_csv()

                # printing some statistics based on num_of_threads, iterations and channel_per_thread
                # printing the header
                print("\n===========================================================================")
                print("CB-PMU PERFORMANCE EVALUATION")
                print("THREADS: ", num_of_threads, " ITERATIONS: ", iterations, " CHANNELS PER THREAD: ", channel_per_thread, "\n")    

                max_time, min_time, mean, median, std_deviation, max_fps, min_fps, mean_fps, median_fps, std_deviation_fps = cb_pmu.print_get_statistics()

                # Write the statistics to the CSV file
                writer.writerow([num_of_threads, channel_per_thread, avg_latency, download_speed, upload_speed,
                                    max_time, min_time, mean, median, std_deviation,
                                    max_fps, min_fps, mean_fps, median_fps, std_deviation_fps])

                print("\n===========================================================================")
