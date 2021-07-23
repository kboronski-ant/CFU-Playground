#!/usr/bin/env python3
# Copyright 2021 The CFU-Playground Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import general
from litex.soc.integration import builder
from litex.soc.integration import soc as litex_soc
from litex.soc.integration.soc import SoCRegion

from litespi.modules import MX25L12833F
from litespi.opcodes import SpiNorFlashOpCodes as Codes
from litespi.phy.generic import LiteSPIPHY
from litespi import LiteSPI

from migen import Signal, If, Module
from litex.soc.interconnect.csr import CSRField
from litex.soc.interconnect.csr import CSRStatus
from litex.soc.interconnect.csr import CSRStorage
from litex.soc.interconnect.csr import AutoCSR

KB = 1024
MB = 1024 * KB


class SpiFlashCounter(Module, AutoCSR):
    def __init__(self, pads):
        self.control = CSRStorage(description="Counter control register",
            fields=[
                CSRField("enable", size=1, description="enable counter"),
                CSRField("reset",  size=1, description="reset counter", pulse=1)
            ])

        self.counter = CSRStatus(description="Counter data register",
            fields=[
                CSRField("clk_ticks", size=32,
                    description="Count the system ticks when the counter is active"),
                CSRField("cs_ticks", size=32,
                    description="Count the system ticks when the counter is active and CS# line is asserted"),
            ])
        cnt_cs = Signal(32)
        cnt_clk = Signal(32)

        self.sync += [
            If(self.control.fields.reset,
                cnt_cs.eq(0),
                cnt_clk.eq(0),
            ).Elif(self.control.fields.enable,
                cnt_clk.eq(cnt_clk+1),
                If(~pads.cs_n,
                    cnt_cs.eq(cnt_cs+1),
                )
            )
        ]

        self.comb += [self.counter.fields.cs_ticks.eq(cnt_cs),
                self.counter.fields.clk_ticks.eq(cnt_clk)]


class LatticeCrossLinkNXEVNSoCWorkflow(general.GeneralSoCWorkflow):
    def make_soc(self, **kwargs) -> litex_soc.LiteXSoC:
        soc = super().make_soc(**kwargs)

        soc.spiflash_region = SoCRegion(0x20000000, 16 * MB, mode="r", cached=True, linker=True)
        spi_platform = soc.platform.request("spiflash4x")
        soc.submodules.spiflash_phy = LiteSPIPHY(
            spi_platform,
            MX25L12833F(Codes.READ_4_4_4, program_cmd=Codes.PP_1_1_1),
            default_divisor=20)
        soc.submodules.spiflash_mmap = LiteSPI(phy=soc.spiflash_phy,
            with_master     = True,
            clk_freq        = soc.sys_clk_freq,
            with_mmap       = True,
            mmap_endianness = soc.cpu.endianness
        )
        soc.constants['FLASH_CHIP_MX25L12833F'] = 1
        soc.constants['FLASH_CHIP_MX25L12833F_QPI'] = 1

        soc.csr.add("spiflash_mmap")
        soc.csr.add("spiflash_phy")
        soc.bus.add_slave(name="spiflash", slave=soc.spiflash_mmap.bus, region=soc.spiflash_region)
        soc.constants['FLASH_BOOT_ADDRESS'] = soc.spiflash_region.origin

        soc.submodules.spi_flash_counter = SpiFlashCounter(spi_platform)
        soc.csr.add("spi_flash_counter")
        soc.constants['LITESPI_CS_COUNTER'] = 1

        return soc

    def build_soc(self, soc: litex_soc.LiteXSoC, **kwargs) -> builder.Builder:
        return super().build_soc(soc, **kwargs)
