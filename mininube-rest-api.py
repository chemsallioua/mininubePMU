from flask import Flask, request, abort
from flask_restful import Api, Resource
import json
from jsonschema import validate, ValidationError
from pmu_estimator import PMUEstimator, EstimatorConfig
import base64
import struct

mininubePMU = Flask(__name__)
api = Api(mininubePMU)

# initialize pmu estimator object
synchestim = PMUEstimator()

class Configure(Resource):

    configuration_schema = {
        "type": "object",
        "properties": {
            "signal": {
                "type": "object",
                "properties": {
                    "n_cycles": {"type": "integer"},
                    "sample_rate": {"type": "integer"},
                    "nominal_freq": {"type": "integer"}
                },
                "required": ["n_cycles", "sample_rate", "nominal_freq"]
            },
            "synchrophasor": {
                "type": "object",
                "properties": {
                    "frame_rate": {"type": "integer"},
                    "number_of_dft_bins": {"type": "integer"},
                    "ipdft_iterations": {"type": "integer"},
                    "iter_e_ipdft_enable": {"type": "integer"},
                    "iter_e_ipdft_iterations": {"type": "integer"},
                    "interference_threshold": {"type": "number"}
                },
                "required": ["frame_rate", "number_of_dft_bins", "ipdft_iterations", "iter_e_ipdft_enable", "iter_e_ipdft_iterations", "interference_threshold"]
            },
            "rocof": {
                "type": "object",
                "properties": {
                    "threshold_1": {"type": "number"},
                    "threshold_2": {"type": "number"},
                    "threshold_3": {"type": "number"},
                    "low_pass_filter_1": {"type": "number"},
                    "low_pass_filter_2": {"type": "number"},
                    "low_pass_filter_3": {"type": "number"}
                },
                "required": ["threshold_1", "threshold_2", "threshold_3", "low_pass_filter_1", "low_pass_filter_2", "low_pass_filter_3"]
            }
        },
        "required": ["signal", "synchrophasor", "rocof"]
    }

    
    
    def post(self):
        data = request.get_json()

        if not data or 'configuration' not in data:
            abort(400)

        configuration = data['configuration']

        try:
            validate(configuration, self.configuration_schema)
        except ValidationError as e:
            abort(400)

        # process_configuration(configuration)
        synchestim_config = EstimatorConfig(
            n_cycles = configuration['signal']['n_cycles'],
            fs = configuration['signal']['sample_rate'],
            f0 = configuration['signal']['nominal_freq'],
            frame_rate = configuration['synchrophasor']['frame_rate'],
            n_bins = configuration['synchrophasor']['number_of_dft_bins'],
            P = configuration['synchrophasor']['ipdft_iterations'],
            iter_eipdft = configuration['synchrophasor']['iter_e_ipdft_enable'],
            Q = configuration['synchrophasor']['iter_e_ipdft_iterations'],
            interf_trig = configuration['synchrophasor']['interference_threshold'],
            rocof_thresh = [configuration['rocof']['threshold_1'], configuration['rocof']['threshold_2'], configuration['rocof']['threshold_3']],
            rocof_low_pass_coeffs= [configuration['rocof']['low_pass_filter_1'] , configuration['rocof']['low_pass_filter_2'], configuration['rocof']['low_pass_filter_3']]
        )
        synchestim.deinit()
        if (synchestim.configure_from_class(synchestim_config) != 0):   
            abort(500)

        return {"status": "Successfully Configured PMU Estimator"}

class Estimate(Resource):

    data_frame_schema = {
        "type": "object",
        "properties": {
            "timestamp": { 
                "type": "object",
                "properties": {
                    "SOC": {"type": "integer", "minimum": 0},
                    "FRACSEC": {"type": "integer", "minimum": 0},
                    "timebase": {"type": "integer", "minimum": 0}
                },
                "required": ["SOC", "FRACSEC", "timebase"]
            },
            "channels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "channel_number": {"type": "integer"},
                        "payload": {"type": "string"}
                    },
                    "required": ["channel_number", "payload"]
                }
            }
        },
        "required": ["timestamp", "channels"]
    }

    def post(self):
        data = request.get_json()

        if not data or 'data_frame' not in data:
            abort(400)

        data_frame = data['data_frame']

        try:
            validate(data_frame, self.data_frame_schema)
        except ValidationError as e:
            print(e)
            abort(400)
        
        # getting the midwindow fracsec
        timebase =data_frame['timestamp']['timebase']

        if timebase != 0:
            mid_window_fracsec = data_frame['timestamp']['FRACSEC']/timebase
        else:
            mid_window_fracsec = 0

        frame = {}
        for channel in data_frame['channels']:
            decoded_data = base64.b64decode(channel['payload'])
            input_signal_window = []
            for i in range(0, len(decoded_data), 8):
                sample = struct.unpack("d", decoded_data[i:i+8])[0]
                input_signal_window.mininubePMUend(sample)    
            estimated_frame = synchestim.estimate(input_signal_window, mid_window_fracsec)
            if estimated_frame is None:
                abort(500)

            frame["channel_" + str(channel['channel_number'])] = estimated_frame
        
        return {"frame": frame}

api.add_resource(Estimate, "/estimate")
api.add_resource(Configure, "/configure")

if __name__ == "__main__":

    mininubePMU.run(debug=False, threaded=True, host='0.0.0.0', port=8080)
