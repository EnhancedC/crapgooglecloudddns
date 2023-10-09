from google.oauth2 import service_account
from google.cloud import dns
from google.api_core.exceptions import NotFound
import google.auth.exceptions
from requests import get
import os
import time
import sys
import argparse
import json
import re
import socket
import logging
import platform
import traceback
















class domainDns(object):
    def __init__(self,authFile,zone,refreshRate) -> None:
        mainLogger.info('Getting Credentials info')
        if authFile:
            if os.path.isfile(os.path.join(authFile)):
                with open(os.path.join(authFile),'r') as jsonInfo:
                    self.authInfo=json.load(jsonInfo)
        else:
            if os.path.isfile(os.path.join(os.path.realpath(sys.path[0]),"auth.json")):
                with open(os.path.join(os.path.realpath(sys.path[0]),"auth.json"),'r') as jsonInfo:
                    self.authInfo=json.load(jsonInfo)
        try:
            self.credentials = service_account.Credentials.from_service_account_info(self.authInfo)
            mainLogger.info('Credentials loaded')
        except ValueError:
            mainLogger.critical('Auth File was not found Or FAILED to load')
            sys.exit()
        self.zone = dns.Client(credentials=self.credentials, project=self.authInfo['project_id']).zone(zone)
        while True:
            try:
                self.reloadZone()
                mainLogger.info('successfully got zone Information')
                break
            except google.auth.exceptions.TransportError:
                mainLogger.error('Failed to connect to oauth2.googleapis.com Retrying in 30 Seconds')
                time.sleep(30)

        self.refreshRate=refreshRate
        self.pubIp=self.getPublicIpAddress() 
        self.currentRecords=None

    @staticmethod
    def getPublicIpAddress():
        while True:
            try:
                mainLogger.info('Connecting to api.ipify.org to get IP address')
                ip=get('https://api.ipify.org',timeout=60).content.decode('utf8')
                socket.inet_aton(ip)
                mainLogger.debug(f'Public Address ->  {ip}')
                return ip
            except socket.gaierror as e:
                mainLogger.error('%s if not an ip address', ip)
                mainLogger.debug(e)
                time.sleep(0.5)
                continue
            except socket.error as e:
                mainLogger.error('Unable to connect to api.ipify.org to get Public IP address\n Waiting 30 Seconds')
                mainLogger.debug(e)
                time.sleep(30)
                continue
            except KeyboardInterrupt:
                mainLogger.warning("KeyboardInterrupt")
                sys.exit()
            except:
                mainLogger.critical(f'{traceback.format_exc()}')

    def addRecord(self, record:str, type:str, ttl:int, data:list ) -> None:
        mainLogger.info('Adding new Record\t%s\t%s\t%s\t%s', record,type,ttl,data)
        record=self.zone.resource_record_set(record,type,ttl,data)
        recordChange=self.zone.changes()
        recordChange.add_record_set(record)
        recordChange.create()
        while recordChange.status != 'done':
            recordChange.reload()
            time.sleep(0.5)
        mainLogger.info('Successfully added Record')
        return

    def changeRecord(self, newRecord:dict, OldRecord) -> None:
        mainLogger.info('Changing Record')
        for record in self.getRecords():
            if newRecord['name'] == record.name and record.record_type == 'A':
                self.deleteRecord(OldRecord.name,OldRecord.record_type,OldRecord.ttl,OldRecord.rrdatas)
 
        self.addRecord(newRecord['name'],newRecord['type'],newRecord['ttl'],newRecord['data'])
        mainLogger.info('Record Change complete')
        
    def deleteRecord(self, record:str, type:str, ttl:int, data:list ) -> None:
        mainLogger.info('Adding new Record\t%s\t%s', record,type)
        currentDdnsRecordInfo=self.zone.resource_record_set(record,type,ttl,data)
        recordChange=self.zone.changes()
        recordChange.delete_record_set(currentDdnsRecordInfo)
        recordChange.create()
        while recordChange.status != 'done':
            recordChange.reload()
            time.sleep(0.5)
        mainLogger.info('Successfully deleted Record')
        return

    def getRecords(self) -> list:
        return self.zone.list_resource_record_sets()
        
    def reloadZone(self):
        while True:
            try:
                mainLogger.info("Loading Zone Information")
                self.zone.reload()
                return
            except KeyboardInterrupt as e:
                
                mainLogger.error(e)
            except:
                mainLogger.warning(f'Error while loading Zone Information')
                mainLogger.critical(f'{traceback.format_exc()}')

     


    @staticmethod
    def getRecordsFromJsonFile() -> dict:
        mainLogger.info('Getting record list')
        try:
            if not os.path.isfile("recordList.json"):
                mainLogger.warning('recordList.json does not exist, creating one')
                with open("recordList.json","x") as file:
                    json.dump({},file)
            with open("recordList.json","r") as file:
                return json.load(file)
        except:
            mainLogger.error("Failed to Load JSON File")
            mainLogger.debug(f"{traceback.format_exc()}")
            return {}


    def updateRecordFromJson(self) -> dict:
        currentIp = self.getPublicIpAddress()
        mainLogger.debug(f'Old Address -> {self.pubIp}')
        jsonRecordsFile = self.getRecordsFromJsonFile()
        if jsonRecordsFile:
            jsonRecords = jsonRecordsFile['zones'][self.zone.name]
        else:
            mainLogger.error(f"No Json Records Loaded Retrying in : {self.refreshRate}s")
            return
        
        if self.currentRecords is None or self.pubIp != currentIp or self.currentRecords != jsonRecords:
            self.currentRecords = jsonRecords
            self.pubIp = currentIp if self.pubIp != currentIp else self.pubIp
            self.reloadZone()
            googleCloudDnsRecords = list(self.getRecords())

            for currentRecord in jsonRecords:
                matchingRecords = [record for record in googleCloudDnsRecords if currentRecord == record.name and record.record_type == "A"]

                if not matchingRecords:
                    mainLogger.info(f'Record "{currentRecord}" with type "A" not found. Creating the record.')
                    self.addRecord(currentRecord, 'A', 300, [currentIp])
                else:
                    mainLogger.info(f'Record "{currentRecord}" with type "A" found.')
                    for record in matchingRecords:
                        if currentIp != record.rrdatas[0]:
                            self.changeRecord({"name": record.name, "type": "A", "ttl": 300, "data": [currentIp]}, record)

        else:
            mainLogger.debug('No Change')



def main(args):
    mainLogger.info('starting Program')
    domain=domainDns(args.auth,args.zone,args.refreshRate)

    while True:
        domain.updateRecordFromJson()
        time.sleep(args.refreshRate)









if __name__ == "__main__":
    agsPrs=argparse.ArgumentParser()
    agsPrs.add_argument('-a','--auth',default=None,type=str,help='Location of auth file Must, be Exact')
    agsPrs.add_argument('-r','--ddnsRecord',default=None,type=str,help="The Record that will automatically be updated")
    agsPrs.add_argument('-t','--refreshRate',default=5,type=int,help="Amount on seconds to wait to check the Public ip Address")
    agsPrs.add_argument('-d','--debug',default=False,action='store_true')
    agsPrs.add_argument('-l','--logfile',default=None,type=str,help='Location to log to')
    agsPrs.add_argument('-v','--verbose',default=0,action='count')
    agsPrs.add_argument('zone',type=str,help='The Zone to be managed')
    args=agsPrs.parse_args()
    mainLogger = logging.getLogger(__name__)
    loggingFileHandler=logging.StreamHandler()
    if args.logfile != None:
        loggingClientHandler=logging.FileHandler(os.path.join(args.logfile))
    else:
        loggingClientHandler=logging.FileHandler(os.path.join(os.path.splitext(f'/var/log/{os.path.basename(__file__)}')[0]+'.log')) if platform.system() == 'Linux' else logging.FileHandler(os.path.join(os.path.realpath(sys.path[0]),f'{os.path.splitext(os.path.basename(__file__))[0]}'+'.log'))
    
    if args.debug:
        mainLogger.setLevel(logging.DEBUG)
        loggingFileHandler.setLevel(logging.DEBUG)
        loggingClientHandler.setLevel(logging.DEBUG)
    else:
        loggingLevel=logging.WARNING if args.verbose == 0 else logging.INFO if args.verbose == 1 else logging.DEBUG
        loggingFileHandler.setLevel(loggingLevel)
        mainLogger.setLevel(loggingLevel)
        loggingClientHandler.setLevel(loggingLevel)
    loggingClientHandler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(funcName)s: %(message)s'))
    loggingFileHandler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(funcName)s: %(message)s'))
    

    
    mainLogger.addHandler(loggingFileHandler)
    mainLogger.addHandler(loggingClientHandler)
    mainLogger.debug('test')

    main(args=args)
