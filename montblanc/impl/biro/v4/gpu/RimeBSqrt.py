#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Simon Perkins
#
# This file is part of montblanc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

import numpy as np
import string

from pycuda.compiler import SourceModule

import montblanc
from montblanc.node import Node

FLOAT_PARAMS = {
    'BLOCKDIMX' : 32,   # Number of channels and polarisations
    'BLOCKDIMY' : 32,    # Number of timesteps
    'BLOCKDIMZ' : 1,    #
    'maxregs'   : 32    # Maximum number of registers
}

# 44 registers results in some spillage into
# local memory
DOUBLE_PARAMS = {
    'BLOCKDIMX' : 32,   # Number of channels and polarisations
    'BLOCKDIMY' : 16,    # Number of timesteps
    'BLOCKDIMZ' : 1,    #
    'maxregs'   : 48    # Maximum number of registers
}

KERNEL_TEMPLATE = string.Template("""
#include \"math_constants.h\"
#include <montblanc/include/abstraction.cuh>
#include <montblanc/include/brightness.cuh>

#define NA (${na})
#define NBL (${nbl})
#define NCHAN (${nchan})
#define NTIME (${ntime})
#define NSRC (${nsrc})
#define NPOL (4)
#define NPOLCHAN (NPOL*NCHAN)

#define BLOCKDIMX (${BLOCKDIMX})
#define BLOCKDIMY (${BLOCKDIMY})
#define BLOCKDIMZ (${BLOCKDIMZ})

template <
    typename T,
    typename Tr=montblanc::kernel_traits<T>,
    typename Po=montblanc::kernel_policies<T> >
__device__
void rime_jones_B_sqrt_impl(
    T * stokes,
    T * alpha,
    T * frequency,
    typename Tr::ct * B_sqrt,
    T ref_freq)
{
    int POLCHAN = blockIdx.x*blockDim.x + threadIdx.x;
    int TIME = blockIdx.y*blockDim.y + threadIdx.y;
    int SRC = blockIdx.z*blockDim.z + threadIdx.z;
    #define POL (threadIdx.x & 0x3)

    if(SRC >= NSRC || TIME >= NTIME || POLCHAN >= NPOLCHAN)
        return;

    __shared__ T freq[BLOCKDIMX];

    // TODO. Using 3 times more shared memory than we
    // really require here, since there's only
    // one frequency per channel.
    if(threadIdx.y == 0 && threadIdx.z == 0)
    {
        freq[threadIdx.x] = frequency[POLCHAN >> 2];
    }

    __syncthreads();

    // Calculate the power term
    int i = SRC*NTIME + TIME;
    typename Tr::ft freq_ratio = freq[threadIdx.x]/ref_freq;
    typename Tr::ft power = Po::pow(freq_ratio, alpha[i]);

    // Read in the stokes parameter,
    // multiplying it by the power term
    i = i*NPOL + POL;
    typename Tr::ft pol = stokes[i]*power;
    typename Tr::ct B_square_root;

    // Create the square root of the brightness matrix
    montblanc::create_brightness_sqrt<T>(B_square_root, pol);

    // Write out the square root of the brightness
    i = (SRC*NTIME + TIME)*NPOLCHAN + POLCHAN;
    B_sqrt[i] = B_square_root;
}

extern "C" {

#define stamp_jones_B_sqrt_fn(ft,ct) \
__global__ void \
rime_jones_B_sqrt_ ## ft( \
    ft * stokes, \
    ft * alpha, \
    ft * frequency, \
    ct * B_sqrt, \
    ft ref_freq) \
{ \
    rime_jones_B_sqrt_impl<ft>(stokes, alpha, \
        frequency, B_sqrt, ref_freq); \
}

stamp_jones_B_sqrt_fn(float,float2);
stamp_jones_B_sqrt_fn(double,double2);

} // extern "C" {
""")

class RimeBSqrt(Node):
    def __init__(self):
        super(RimeBSqrt, self).__init__()

    def initialise(self, solver, stream=None):
        slvr = solver

        self.polchans = 4*slvr.nchan

        # Get a property dictionary off the solver
        D = slvr.get_properties()
        # Include our kernel parameters
        D.update(FLOAT_PARAMS if slvr.is_float() else DOUBLE_PARAMS)

        # Update kernel parameters to cater for radically
        # smaller problem sizes. Caters for a subtle bug
        # with Kepler shuffles and warp sizes < 32
        if self.polchans < D['BLOCKDIMX']: D['BLOCKDIMX'] = self.polchans
        if slvr.ntime < D['BLOCKDIMY']: D['BLOCKDIMY'] = slvr.ntime
        if slvr.nsrc < D['BLOCKDIMZ']: D['BLOCKDIMZ'] = slvr.nsrc

        regs = str(FLOAT_PARAMS['maxregs'] \
                if slvr.is_float() else DOUBLE_PARAMS['maxregs'])

        kname = 'rime_jones_B_sqrt_float' \
            if slvr.is_float() is True else \
            'rime_jones_B_sqrt_double'

        kernel_string = KERNEL_TEMPLATE.substitute(**D)
        self.mod = SourceModule(kernel_string,
            options=['-lineinfo','-maxrregcount', regs],
            include_dirs=[montblanc.get_source_path()],
            no_extern_c=True)

        self.kernel = self.mod.get_function(kname)
        self.launch_params = self.get_launch_params(slvr, D)

    def shutdown(self, solver, stream=None):
        pass

    def pre_execution(self, solver, stream=None):
        pass

    def get_launch_params(self, slvr, D):
        polchans_per_block = D['BLOCKDIMX']
        times_per_block = D['BLOCKDIMY']
        srcs_per_block = D['BLOCKDIMZ']

        polchan_blocks = self.blocks_required(self.polchans, polchans_per_block)
        time_blocks = self.blocks_required(slvr.ntime, times_per_block)
        src_blocks = self.blocks_required(slvr.nsrc, srcs_per_block)

        return {
            'block' : (polchans_per_block, times_per_block, srcs_per_block),
            'grid'  : (polchan_blocks, time_blocks, src_blocks),
        }

    def execute(self, solver, stream=None):
        slvr = solver

        self.kernel(slvr.stokes_gpu, slvr.alpha_gpu,
            slvr.frequency_gpu, slvr.B_sqrt_gpu,
            slvr.ref_freq,
            stream=stream, **self.launch_params)

    def post_execution(self, solver, stream=None):
        pass