import torch
import numpy as np
import scipy as sp
from scipy.stats import multivariate_normal
from src.utils.rand import RandomAgent, ReplayBuffer
from ..agents.base import PTACNetwork, PTAgent, Conv, one_hot_from_indices

class MPPIController(RandomAgent):
	def __init__(self, state_size, action_size, envmodel, config, gpu=True):
		self.envmodel = envmodel(state_size, action_size, config, load=config.env_name)
		self.mu = np.zeros(action_size)
		self.cov = np.diag(np.ones(action_size))*0.5
		self.icov = np.linalg.inv(self.cov)
		self.lamda = config.MPC.LAMBDA
		self.horizon = config.MPC.HORIZON
		self.nsamples = config.MPC.NSAMPLES
		self.control = np.random.uniform(-1, 1, [self.horizon, *action_size])
		self.noise = np.random.multivariate_normal(self.mu, self.cov, size=(self.nsamples, self.horizon))
		self.init_cost = np.sum(self.control[None,:,None,:] @ self.icov[None,None,:,:] @ self.noise[:,:,:,None], axis=(1,2,3))
		self.config = config
		self.step = 0

	def get_action(self, state, eps=None, sample=True):
		self.step += 1
		if self.step%self.config.MPC.get("CONTROL_FREQ",1) == 0:
			x = torch.Tensor(state).view(1,-1).repeat(self.nsamples, 1)
			controls = np.clip(self.control[None,:,:] + self.noise, -1, 1)
			self.envmodel.reset(batch_size=self.nsamples, state=x)
			self.states, rewards = zip(*[self.envmodel.step(controls[:,t], numpy=True) for t in range(self.horizon)])
			costs = -np.sum(rewards, 0) #+ self.lamda * np.copy(self.init_cost)
			beta = np.min(costs)
			costs_norm = -(costs - beta)/self.lamda
			weights = sp.special.softmax(costs_norm)
			self.control += np.sum(weights[:,None,None]*self.noise, 0)
		action = np.tanh(self.control[0])
		self.control = np.roll(self.control, -1, axis=0)
		self.control[-1] = 0
		return action if len(action.shape)==len(state.shape) else np.repeat(action[None,:], state.shape[0], 0)

	def train(self, state, action, next_state, reward, done):
		pass

