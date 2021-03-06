#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  gearmanin.py
#
#  Copyright 2014 Jelle Smet <development@smetj.net>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

from wishbone import Actor
from gevent import spawn, sleep
from gevent import monkey
monkey.patch_select()
monkey.patch_socket()
from gearman import GearmanWorker
from Crypto.Cipher import AES
import base64


class GearmanIn(Actor):

    '''**Consumes events/jobs from  Gearmand.**

    Consumes jobs from a Gearmand server.
    When secret is none, no decryption is done.


    Parameters:

        - name(str)
           |  The name of the module.

        - size(int)
           |  The default max length of each queue.

        - frequency(int)
           |  The frequency in seconds to generate metrics.

        - hostlist(list)(["localhost:4730"])
           |  A list of gearmand servers.  Each entry should have
           |  format host:port.

        - secret(str)(None)
           |  The AES encryption key to decrypt Mod_gearman messages.

        - workers(int)(1)
           |  The number of gearman workers within 1 process.

        - queue(str)(wishbone)
           |  The queue to consume jobs from.


    Queues:

        - outbox:   Outgoing events.

    '''

    def __init__(self, name, size, frequency, hostlist=["localhost:4730"], secret=None, workers=1, queue="wishbone"):
        Actor.__init__(self, name, size, frequency)
        self.pool.createQueue("outbox")
        self.name = name
        self.hostlist = hostlist
        self.secret = secret
        self.workers = workers
        self.queue = queue

        self.background_instances = []

        if self.secret is None:
            self.decrypt = self.__plainTextJob
        else:
            key = self.secret[0:32]
            self.cipher = AES.new(key + chr(0) * (32 - len(key)))
            self.decrypt = self.__encryptedJob

    def preHook(self):
        for _ in range(self.workers):
            spawn(self.gearmanWorker)

    def consume(self, gearman_worker, gearman_job):
        decrypted = self.decrypt(gearman_job.data)
        self.submit({"header": {}, "data": decrypted}, self.pool.queue.outbox)
        return decrypted

    def __encryptedJob(self, data):
        return self.cipher.decrypt(base64.b64decode(data))

    def __plainTextJob(self, data):
        return data

    def gearmanWorker(self):

        self.logging.info("Gearmand worker instance started")
        while self.loop():
            try:
                worker_instance = GearmanWorker(self.hostlist)
                worker_instance.register_task(self.queue, self.consume)
                worker_instance.work()
            except Exception as err:
                self.logging.warn('Connection to gearmand failed. Reason: %s. Retry in 1 second.' % err)
                sleep(1)
