#%%
# Copyright (c) 2024 M Ganesh Kumar
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from env import *
from utils import *
from model import *

import os
os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = "0.2"
import jax.numpy as jnp
import numpy as np
from jax import config
config.update('jax_platform_name', 'cpu')
from jax.lib import xla_bridge
device = xla_bridge.get_backend().platform
print(device)

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--episodes', type=int, required=False, help='episodes', default=50000)
parser.add_argument('--tmax', type=int, required=False, help='tmax', default=100)

parser.add_argument('--goalcoords', type=float,nargs='+', required=False, help='goal coords', default=[[0.5]])
parser.add_argument('--startcoods', type=float,nargs='+', required=False, help='start coods', default=[-0.75])
parser.add_argument('--rsz', type=float, required=False, help='reward radius', default=0.05)
parser.add_argument('--rmax', type=int, required=False, help='max rewards to accumulate', default=5)

parser.add_argument('--seed', type=int, required=False, help='seed', default=0)
parser.add_argument('--pcinit', type=str, required=False, help='homogeneous or heterogenous field population', default='homo')
parser.add_argument('--bptype', type=str, required=False, help='backprop TD error using', default='both')
parser.add_argument('--npc', type=int, required=False, help='number of fields', default=64)
parser.add_argument('--alpha', type=float, required=False, help='alpha init', default=1)
parser.add_argument('--sigma', type=float, required=False, help='sigma init', default=0.1)

parser.add_argument('--plr', type=float, required=False, help='actor learning rate', default=0.01)
parser.add_argument('--clr', type=float, required=False, help='critic lr', default=0.01)
parser.add_argument('--llr', type=float, required=False, help='lambda lr', default=0.0001) 
parser.add_argument('--alr', type=float, required=False, help='alpha lr', default=0.0001) 
parser.add_argument('--slr', type=float, required=False, help='sigma lr', default=0.0001)
parser.add_argument('--gamma', type=float, required=False, help='gamma', default=0.9)
parser.add_argument('--nact', type=int, required=False, help='number of actions', default=2)
parser.add_argument('--beta', type=float, required=False, help='action beta', default=1)

parser.add_argument('--bsigma', type=float, required=False, help='L2 penalty for sigma', default=0.0)
parser.add_argument('--balpha', type=float, required=False, help='L2 penalty for alpha', default=0.0)
parser.add_argument('--sigmaclip', type=float, required=False, help='clip to max sigma value', default=0.0)
parser.add_argument('--alphaclip', type=float, required=False, help='clip to max alpha value', default=0.0)

parser.add_argument('--paramsindex', type=int,nargs='+', required=False, help='which params to add noise to', default=[0,1,2])
parser.add_argument('--noise', type=float, required=False, help='noise variance magnitude', default=0.00)

parser.add_argument('--analysis', type=str, required=False, help='analysis', default='na')
parser.add_argument('--datadir', type=str, required=False, help='datadir', default='./data/')
parser.add_argument('--figdir', type=str, required=False, help='figdir', default='./fig/')

args, unknown = parser.parse_known_args()
print(args)


# training params
train_episodes = args.episodes
tmax = args.tmax

# env pararms
envsize = 1
maxspeed = 0.1
goalsize = args.rsz
startcoord = args.startcoods
goalcoords = args.goalcoords
seed = args.seed
max_reward = args.rmax

#agent params
npc = args.npc
sigma = args.sigma
alpha = args.alpha
nact = args.nact

# noise params
noise = args.noise
paramsindex = args.paramsindex
piname = ''.join(map(str, paramsindex))
pcinit = args.pcinit

actor_eta = args.plr
critic_eta = args.clr
pc_eta = args.llr
sigma_eta = args.slr
constant_eta = args.alr
etas = [pc_eta, sigma_eta,constant_eta, actor_eta,critic_eta]
betas = [0.5,args.balpha]  # beta for critic is 0.5
gamma = args.gamma

savevar = False
savefig = False
exptname = f'1D_td_{nact}a_{npc}n_{seed}s_{train_episodes}e_{goalsize}gs_{actor_eta}plr_{pc_eta}llr_{constant_eta}alr_{sigma_eta}slr_{args.balpha}ba'
figdir = './fig/'
datadir = './data/'

if pcinit=='homo':
    params = uniform_pc_weights(npc, nact, seed, sigma=sigma, alpha=alpha, envsize=envsize)
elif pcinit == 'hetero':
        params = random_all_pc_weights(npc, nact, seed, sigma=sigma, alpha=alpha, envsize=envsize)

initparams = params.copy()
initpcacts = plot_place_cells(initparams, startcoord=startcoord, goalcoord=flatten([goalcoords[0]]),goalsize=goalsize, title='Fields before learning',envsize=envsize)

# inner loop training loop
def run_trial(params, env):
    coords = []
    actions = []
    rewards = []

    state, goal, eucdist, done = env.reset()
    totR = 0
    
    for t in range(tmax):

        pcact = predict_placecell(params, state)

        aprob = predict_action_prob(params, pcact)

        onehotg = get_onehot_action(aprob, nact=nact)

        newstate, reward, done = env.step(onehotg) 

        coords.append(state)
        actions.append(onehotg)
        rewards.append(reward)

        state = newstate.copy()

        totR += reward

        if done:
            coords.append(newstate)  # include new state for value computation
            break

    return jnp.array(coords), jnp.array(rewards).reshape(-1), jnp.array(actions), t


#%%
losses = []
latencys = []
allcoords = []
logparams = []
logparams.append(initparams)
allrewards = []

for goalcoord in goalcoords:
    env = OneDimNav(startcoord=startcoord, goalcoord=[goalcoord], goalsize=goalsize, tmax=tmax, 
                    maxspeed=maxspeed,envsize=envsize, nact=nact, max_reward=max_reward)

    for episode in range(train_episodes):

        coords, rewards, actions, latency = run_trial(params, env)
        
        params, grads, loss = update_td_params(params, coords, actions, rewards, etas, gamma, betas)

        allcoords.append(coords)
        logparams.append(params)
        latencys.append(latency)
        losses.append(loss)
        allrewards.append(env.total_reward[0,0])

        print(f'Trial {episode+1}, G {allrewards[-1]:.3f}, t {latency}, L {loss:.3f}, a {np.max(params[2]):.3f}')


if savevar:
    saveload(datadir+'full_'+exptname, [logparams, allrewards, allcoords], 'save')

env.plot_trajectory()

f = plot_analysis(logparams, allrewards, allcoords, train_episodes//2, exptname=exptname, rsz=goalsize)

if savefig:
    f.savefig(figdir+exptname+'.png')
