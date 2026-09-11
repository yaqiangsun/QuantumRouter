import time
from collections import defaultdict
import numpy as np
from qiskit.providers import JobV1, JobStatus
from qiskit.providers.backend import Backend
from qiskit.result import Result
from .client import LingYunApiClient


class LingYunJob(JobV1):
    """
    A class representing a job executed on the LingYun quantum computing platform.
    """
    def __init__(
        self,
        job_id: str,
        backend: Backend | None = None,
        api_client: LingYunApiClient | None = None,
        **kwargs
    ) -> None:
        """
        Initializes the LingYunJob instance.

        Args:
            job_id (str): Unique identifier of the submitted experiment task.
            backend (Backend | None): Target quantum backend instance, default None.
            api_client (LingYunApiClient | None): HTTP client for LingYun backend API, default None.
            **kwargs: Extended metadata arguments such as shot count, readout calibration switch.
        """
        super().__init__(backend=backend, job_id=job_id,** kwargs)
        if api_client is None:
            self._api_client = LingYunApiClient()
        self._api_client = api_client
        self._readout_matrix_cache = {}

    def submit(self):
        """Empty placeholder for job submission logic, to be implemented later."""
        pass

    def cancel(self):

        raise NotImplementedError("LingYun backend does not support job cancel")

    def status(self) -> JobStatus:
        """
        Query current execution status of the submitted quantum task.

        Returns:
            JobStatus: Enumerated job state including DONE, RUNNING, QUEUED.
        """
        task_id_arr = self._job_id.split(',')
        resp_data = self._api_client.query_job(task_id_arr)
        received_task_cnt = len(resp_data)

        if received_task_cnt == len(task_id_arr):
            return JobStatus.DONE
        elif received_task_cnt > 0:
            return JobStatus.RUNNING
        return JobStatus.QUEUED

    def result(self) -> Result:
        """Retrieves the results of the job.
        Returns:
            Result: The results of the job, including counts and memory data.
    
        Raises:
            Exception: If the job fails to complete or retrieve results.
        """
        task_id_arr = self._job_id.split(',')
        while True:
            current_state = self.status()
            if current_state == JobStatus.DONE:
                break
            time.sleep(1)

        experiment_result_list = []
        raw_task_items = self._api_client.query_job(task_id_arr)
        for task_item in raw_task_items:
            enable_readout_cal = self.metadata.get("readout_calibration", True)
            shot_total = self.metadata.get("shots", len(task_item["resultStatus"]) - 1)

            if self._backend.simulator or not enable_readout_cal:
                # Simulator branch: extract raw binary measurement matrix
                raw_sample_matrix = self._extract_measure_raw_data(task_item)
                # Convert raw boolean samples to hex-formatted shot counts and memory records
                shot_counter, shot_memory_records = self._convert_sample_to_hex_counts(raw_sample_matrix)
                # print("[INFO] Verify consistency of count and memory outputs: ", shot_counter, shot_memory_records)
            else:
                # Physical hardware branch: load hardware calibration parameters
                hardware_cfg = self._backend._machine_config
                # Calculate readout-error-corrected probability distribution
                prob_dist_data = self._compute_corrected_prob_dist(task_item, hardware_cfg)
                # Map corrected probability distribution to discrete shot counts
                shot_counter, shot_memory_records = self._prob_to_shot_statistics(prob_dist_data, shot_total)

            exp_data_block = {
                "shots": shot_total,
                "success": True,
                "data": {
                    "counts": shot_counter,
                    "memory": shot_memory_records
                }
            }
            experiment_result_list.append(exp_data_block)

        final_result = Result.from_dict({
            "backend_name": self._backend.configuration.backend_name,
            "backend_version": "1.0",
            "qobj_id": str(id(self._job_id)),
            "job_id": self._job_id,
            "success": True,
            "status": JobStatus.DONE.name,
            "results": experiment_result_list
        })
        return final_result

    @staticmethod
    def _convert_sample_to_hex_counts(sample_bool_matrix):
        """
        Aggregate boolean measurement sample matrix into hexadecimal state counts and raw shot memory list.
        """
        if isinstance(sample_bool_matrix[0], bool):
            sample_bool_matrix = [sample_bool_matrix]
        transposed_samples = np.transpose(sample_bool_matrix)
        record_storage = []
        count_mapping = defaultdict(int)

        # Iterate over each single-shot measurement record
        for sample_line in transposed_samples:
            state_decimal = 0
            qubit_dim = len(sample_bool_matrix)
            for qubit_idx in range(qubit_dim):
                bit_val = sample_line[qubit_idx]
                state_decimal += bit_val * (2 ** qubit_idx)
            hex_state_key = hex(state_decimal)
            count_mapping[hex_state_key] += 1
            record_storage.append(hex_state_key)

        # Convert temporary counter to standard dict and isolate memory list
        final_count_dict = dict(count_mapping)
        memory_list = record_storage
        return final_count_dict, memory_list

    @staticmethod
    def _prob_to_shot_statistics(prob_dist_map, total_shots):
        """
        Convert calibrated continuous probability distribution to discrete integer shot counts and shuffled memory records.
        """
        bin_state_labels = []
        prob_values = []
        for bin_str, prob in prob_dist_map.items():
            bin_state_labels.append(hex(int(bin_str, 2)))
            prob_values.append(prob)

        # Clip probabilities to valid range [0, 1] and perform normalization
        clipped_probs = np.clip(prob_values, a_min=0.0, a_max=1.0)
        prob_sum = clipped_probs.sum()
        normalized_probs = clipped_probs / prob_sum

        # Calculate base integer shot allocation and residual fractional shots
        exact_float_counts = total_shots * normalized_probs
        base_counts = exact_float_counts.astype(np.int64)
        fractional_remain = exact_float_counts - base_counts
        leftover_shot_num = total_shots - base_counts.sum()

        if leftover_shot_num > 0:
            # Distribute residual shots to states with largest fractional remainders
            priority_index = np.argpartition(-fractional_remain, leftover_shot_num)[:leftover_shot_num]
            base_counts[priority_index] += 1

        # Filter zero-count states and generate full shot memory array
        count_dict = {}
        for idx, cnt in enumerate(base_counts):
            if cnt > 0:
                count_dict[bin_state_labels[idx]] = int(cnt)
        memory_array = np.repeat(bin_state_labels, base_counts)
        np.random.shuffle(memory_array)
        memory_output = memory_array.tolist()
        return count_dict, memory_output

    def _extract_measure_raw_data(self, task_result: dict):
        """
        Parse raw resultStatus string payload returned by LingYun server, output per-qubit boolean measurement matrix.
        """
        raw_sample_arr = task_result.get("resultStatus", [])
        # print("[DEBUG] raw sample array length:", len(raw_sample_arr), raw_sample_arr[:3])
        # Concatenate all digit strings, skip first row which stores qubit index identifiers
        full_sample_text = ""
        for single_qubit_record in raw_sample_arr[1:]:
            digit_str = "".join([str(bit) for bit in single_qubit_record])
            full_sample_text += digit_str
        # print("[DEBUG] total sample string length:", len(full_sample_text))

        qubit_channel_count = len(raw_sample_arr[0])
        # print("[DEBUG] measured qubit channel count:", qubit_channel_count)
        qubit_sample_matrix = []
        # Slice concatenated string to isolate measurement sequence for each qubit
        for qubit_channel in range(qubit_channel_count):
            channel_samples = full_sample_text[qubit_channel::qubit_channel_count]
            bool_sample_line = [bit_char == "1" for bit_char in channel_samples]
            qubit_sample_matrix.append(bool_sample_line)
            # print("[DEBUG] single qubit sample size:", len(bool_sample_line))
        return qubit_sample_matrix

    def _compute_corrected_prob_dist(self, task_result: dict, hardware_config: dict):
        """
        Load hardware readout fidelity parameters, construct inverse confusion matrix to eliminate measurement readout bias.
        """
        # print("[DEBUG] start readout calibration with raw task data:", task_result)
        qubit_id_list = task_result["resultStatus"][0]
        measure_qubit_labels = [f"Q{idx}" for idx in qubit_id_list]
        qubit_total = len(measure_qubit_labels)

        # 读取硬件保真度
        readout_section = hardware_config["readout"]["readoutArray"]
        used_qubit_ids = readout_section["|0> readout fidelity"]["qubit_used"]
        f0_param_list = readout_section["|0> readout fidelity"]["param_list"]
        f1_param_list = readout_section["|1> readout fidelity"]["param_list"]

        qubit_fidelity_pairs = []
        for q_label in measure_qubit_labels:
            pos = used_qubit_ids.index(q_label)
            f0_val = float(f0_param_list[pos])
            f1_val = float(f1_param_list[pos])
            qubit_fidelity_pairs.append([f0_val, f1_val])

        # Compute uncorrected full-state probability distribution from raw samples
        raw_sample_mat = self._extract_measure_raw_data(task_result)
        original_prob_dist = self._build_full_state_probability(raw_sample_mat, qubit_total)
        prob_vector = np.array(list(original_prob_dist.values()), ndmin=2).T

        # to avoid redundant computation
        cache_key = tuple(np.array(qubit_fidelity_pairs).flatten())
        if cache_key not in self._readout_matrix_cache:
            inv_combined_matrix = np.array([[1.0]])
            # Construct global inverse matrix via Kronecker product from last qubit to first
            for f0, f1 in reversed(qubit_fidelity_pairs):
                denom = f0 + f1 - 1.0
                if abs(denom) < 1e-12:
                    raise Exception(f"Invalid readout fidelity pair [{f0}, {f1}], cannot calibrate")
                single_qubit_inv_cm = np.array([
                    [f1, f1 - 1.0],
                    [f0 - 1.0, f0]
                ]) / denom
                inv_combined_matrix = np.kron(single_qubit_inv_cm, inv_combined_matrix)
            self._readout_matrix_cache[cache_key] = inv_combined_matrix
        final_inv_cm = self._readout_matrix_cache[cache_key]

        # apply readout error correction
        calibrated_prob_vec = np.dot(final_inv_cm, prob_vector)
        calibrated_prob_map = {}
        for state_idx, prob_val in enumerate(calibrated_prob_vec):
            bin_state_key = bin(state_idx)[2:].zfill(qubit_total)
            calibrated_prob_map[bin_state_key] = prob_val[0]
        return calibrated_prob_map

    @staticmethod
    def _build_full_state_probability(bool_sample_matrix, qubit_count):
        """
        Calculate complete probability distribution covering all computational basis states, including zero-probability entries.
        """
        if isinstance(bool_sample_matrix[0], bool):
            bool_sample_matrix = [bool_sample_matrix]
        total_state_num = 2 ** qubit_count
        state_count_storage = np.zeros(total_state_num, dtype=int)
        transposed_sample_lines = np.transpose(bool_sample_matrix)
        shot_amount = len(transposed_sample_lines)

        # # 逐采样统计十进制态计数
        for shot_row in transposed_sample_lines:
            dec_state = 0
            for q_idx in range(qubit_count):
                bit = shot_row[q_idx]
                dec_state += bit * (2 ** q_idx)
            state_count_storage[dec_state] += 1

        # Normalize shot counts to acquire state probability values
        full_prob_dist = {}
        for state_dec in range(total_state_num):
            bin_str = bin(state_dec)[2:].zfill(qubit_count)
            full_prob_dist[bin_str] = state_count_storage[state_dec] / shot_amount
        return full_prob_dist
