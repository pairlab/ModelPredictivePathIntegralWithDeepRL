import os
import glob
import torch
import numpy as np
from bisect import bisect
from .data import get_data_dir
from sklearn.model_selection import train_test_split

class RolloutDataset(torch.utils.data.Dataset): 
	def __init__(self, config, buffer_size=10000, train=True): 
		self.root = get_data_dir(config.env_name, config.get("model"))
		self._files = sorted([os.path.join(self.root, f) for f in glob.glob(f"{self.root}/**/*.npz", recursive=True)])
		self._files = train_test_split(self._files, train_size=config.train_prop, shuffle=True, random_state=config.SEED)[1-int(train)]
		self._cum_size = None
		self._buffer = None
		self._buffer_fnames = None
		self._buffer_index = 0
		self._buffer_size = buffer_size
		self.load_next_buffer()

	def load_next_buffer(self):
		self._buffer_fnames = self._files[self._buffer_index:self._buffer_index + self._buffer_size]
		self._buffer_index += len(self._buffer_fnames)
		self._buffer_index = self._buffer_index % len(self._files)
		self._buffer = []
		self._cum_size = [0]
		for f in self._buffer_fnames:
			with np.load(f) as data:
				self._buffer += [{k: np.copy(v) for k, v in data.items()}]
				self._cum_size += [self._cum_size[-1] + self._data_per_sequence(data['rewards'].shape[0])]

	def __len__(self):
		return self._cum_size[-1]

	def __getitem__(self, i):
		file_index = bisect(self._cum_size, i) - 1
		seq_index = i - self._cum_size[file_index]
		data = self._buffer[file_index]
		return self._get_data(data, seq_index)

	def _get_data(self, data, seq_index):
		pass

	def _data_per_sequence(self, data_length):
		pass

class OnlineDataset(torch.utils.data.Dataset): 
	def __init__(self, config, buffer, seq_len, train=True): 
		self.buffer = buffer
		self.cum_size = [0]
		self.seq_len = min(seq_len, np.min([len(x[3]) for x in buffer]))
		for states, actions, next_states, rewards, dones in self.buffer:
			self.cum_size += [self.cum_size[-1] + self._data_per_sequence(rewards.shape[0])]

	def __len__(self):
		return self.cum_size[-1]

	def __getitem__(self, i):
		file_index = bisect(self.cum_size, i) - 1
		seq_index = i - self.cum_size[file_index]
		data = self.buffer[file_index]
		return self._get_data(data, seq_index)

	def _get_data(self, data, seq_index):
		states_data = data[0][seq_index:seq_index + self.seq_len + 1]
		states, next_states = states_data[:-1], states_data[1:]
		actions = data[1][seq_index+1:seq_index + self.seq_len + 1].astype(np.float32)
		rewards = data[3][seq_index+1:seq_index + self.seq_len + 1].astype(np.float32)
		dones = data[4][seq_index+1:seq_index + self.seq_len + 1].astype(np.float32)
		return states, actions, next_states, rewards, dones

	def _data_per_sequence(self, data_length):
		return data_length - self.seq_len

class RolloutSequenceDataset(RolloutDataset): 
	""" Encapsulates rollouts.

		Rollouts should be stored in subdirs of the root directory, in the form of npz files,
		each containing a dictionary with the keys:
			- states: (rollout_len, *states_shape)
			- actions: (rollout_len, action_size)
			- rewards: (rollout_len,)
			- terminals: (rollout_len,), boolean

		As the dataset is too big to be entirely stored in rams, only chunks of it
		are stored, consisting of a constant number of files (determined by the
		buffer_size parameter).  Once built, buffers must be loaded with the
		load_next_buffer method.

		Data are then provided in the form of tuples (states, actions, next_states, reward, dones):
		- states: (seq_len, *states_shape)
		- actions: (seq_len, action_size)
		- reward: (seq_len,)
		- dones: (seq_len,) boolean
		- next_states: (seq_len, *states_shape)

		NOTE: seq_len < rollout_len in moste use cases

		:args root: root directory of data sequences
		:args seq_len: number of timesteps extracted from each rollout
		:args transform: transformation of the states
		:args train: if True, train data, else test
	"""
	def __init__(self, config, buffer_size=10000, train=True): 
		self._seq_len = config.seq_len
		super().__init__(config, buffer_size, train)

	def _get_data(self, data, seq_index):
		states_data = data['states'][seq_index:seq_index + self._seq_len + 1]
		states, next_states = states_data[:-1], states_data[1:]
		actions = data['actions'][seq_index+1:seq_index + self._seq_len + 1].astype(np.float32)
		rewards = data['rewards'][seq_index+1:seq_index + self._seq_len + 1].astype(np.float32)
		dones = data['dones'][seq_index+1:seq_index + self._seq_len + 1].astype(np.float32)
		return states, actions, next_states, rewards, dones

	def _data_per_sequence(self, data_length):
		return data_length - self._seq_len

class RolloutExperienceDataset(RolloutDataset): 
	""" Encapsulates rollouts.

		Rollouts should be stored in subdirs of the root directory, in the form of npz files,
		each containing a dictionary with the keys:
			- states: (rollout_len, *states_shape)
			- actions: (rollout_len, action_size)
			- rewards: (rollout_len,)
			- terminals: (rollout_len,), boolean

		As the dataset is too big to be entirely stored in rams, only chunks of it
		are stored, consisting of a constant number of files (determined by the
		buffer_size parameter).  Once built, buffers must be loaded with the
		load_next_buffer method.

		Data are then provided in the form of images

		:args root: root directory of data sequences
		:args seq_len: number of timesteps extracted from each rollout
		:args transform: transformation of the states
		:args train: if True, train data, else test
	"""
	def _data_per_sequence(self, data_length):
		return data_length

	def _get_data(self, data, seq_index):
		state = data["states"][seq_index]
		action = data["actions"][seq_index]
		next_state = data["states"][seq_index+1] if seq_index+1 < len(data["states"])-1 else state*0
		reward = data["rewards"][seq_index]
		done = data["dones"][seq_index]
		exp = (state, action, next_state, reward, done)
		return exp