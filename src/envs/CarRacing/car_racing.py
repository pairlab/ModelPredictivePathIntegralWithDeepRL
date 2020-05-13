import os
import sys
import numpy as np
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel
from mlagents_envs import logging_util
from .unity_gym import UnityToGymWrapper
from .objective import CostModel
from ..Gym import gym

logging_util.set_log_level(logging_util.ERROR)

class EnvMeta(type):
	def __new__(meta, name, bases, class_dict):
		cls = super().__new__(meta, name, bases, class_dict)
		gym.register(f"{name}-v1", entry_point=cls)
		return cls

class CarRacing(gym.Env, metaclass=EnvMeta):
	def __new__(cls, **kwargs):
		cls.id = getattr(cls, "id", 0)+1
		return super().__new__(cls, **kwargs)

	def __init__(self, max_time=1000):
		root = os.path.dirname(os.path.abspath(__file__))
		sim_file = os.path.abspath(os.path.join(root, "simulator", sys.platform, "CarRacing"))
		self.channel = EngineConfigurationChannel()
		unity_env = UnityEnvironment(file_name=sim_file, side_channels=[self.channel], worker_id=self.id + np.random.randint(10000, 20000))
		self.scale_sim = lambda s: self.channel.set_configuration_parameters(width=50*int(1+9*s), height=50*int(1+9*s), quality_level=int(1+3*s), time_scale=int(1+5*(1-s)))
		self.env = UnityToGymWrapper(unity_env)
		self.action_space = self.env.action_space
		self.observation_space = self.env.observation_space
		self.cost_model = CostModel()
		self.max_time = max_time
		self.reset()

	def reset(self, idle_timeout=None, train=True):
		self.time = 0
		self.scale_sim(0)
		self.idle_timeout = idle_timeout if isinstance(idle_timeout, int) else np.Inf
		state = self.env.reset()
		return state

	def get_reward(self, state):
		x, _, y = state[:3]
		vel = state[3:6]
		reward = np.linalg.norm(vel) - self.cost_model.get_cost((x,y))
		return 0.1*reward

	def step(self, action):
		self.time += 1
		state, reward, done, info = self.env.step(action)
		reward = self.get_reward(state)
		idle = state[-1]
		done = done or idle>self.idle_timeout or self.time > self.max_time
		return state, reward, done, info

	def render(self, mode=None, **kwargs):
		self.scale_sim(1)
		return self.env.render()

	def close(self):
		if not hasattr(self, "closed"): self.env.close()
		self.closed = True
