#Description: Script that gets the ip from the a selection of different types of devices.
#Need to install python requests module for script to function
import base64
import ssl
import requests
#from requests import session
import json
import getpass
import csv
from collections import defaultdict
import sys
import os
#import urllib3

#Note: if you're searching an ip address that has multiple data sources, the search will only return the
#		result of the first one the script finds
#Gets the a devices unique id
def getDSid(dataName):
	params = {"types": ["THIRD_PARTY"],"filterByRights" : "false"}
	params_json = json.dumps(params)
	DeviceTreeURL = "https://<url of ESM>/rs/esm/devGetDeviceList"
	response = requests.post(DeviceTreeURL, data=params_json, headers=payloadID, verify=False)
	data = response.json()
	DSid = ""
	for item in data.get('return'):
		if item.get('name').lower() == dataName.lower():
			DSid = item.get('id').get('id')
	return DSid

#Builds a config json object for the query based on the device id. Used for the qryExecuteDetail command
def build_config(value):
    time_range = "LAST_24_HOURS"
    # Query
    qconf = {"config": {
               "limit" : 100,
               "timeRange": time_range,
               "order": [{"direction": "ASCENDING",
                          "field": {"name": "FirstTime"}
                        }],
               "fields": [{"name": "FirstTime"},
                           {"name" : "EventCount"}],
               "filters": [{"type": "EsmFieldFilter", 
                            "field": {"name": "IPSID"},
                            "operator": "IN","values": 
                          [{"type": "EsmBasicValue", "value": value}]}]
        }          }
    return(json.dumps(qconf))

# Execute the query on the device's unique id
def query_esm(qconf_json):
	DeviceTreeURL = "https://<url of ESM>/rs/esm/"
	result = requests.post(DeviceTreeURL + 'qryExecuteDetail?type=EVENT&reverse=False', headers=payloadID, data=qconf_json, verify=False)
	result_dict = result.json()
	queryID = result_dict.get("return").get("resultID").get("value")
	qconf = {"resultID": {"value": queryID}}
	qconf_json = json.dumps(qconf)
	result = requests.post(DeviceTreeURL + 'qryGetStatus',headers=payloadID, data=qconf_json, verify=False)
	result_dict = result.json()
	status = result_dict.get("return").get("complete")
	while not status:
		#time.sleep(10)
		result = requests.post(DeviceTreeURL + 'qryGetStatus',headers=payloadID, data=qconf_json, verify=False)
		result_dict = result.json()
		status = result_dict.get("return").get("complete")
	total_records = result_dict.get("return").get("totalRecords")
	return(qconf_json, total_records)

#For the device, sees if the device is logging events for the current day
def get_results(qconf_json, total_records, dsname): 
	record_pos = 0
	records_got = 0
	result_dict = {}
	records_dict = {}
	event_total = 0
	total_events = 0
	count = 0
	DeviceTreeURL = "https://<url of ESM>/rs/esm/"        
	while record_pos < total_records:
		result = requests.post("https://<url of ESM>/rs/esm/" + 'qryGetResults?startPos=' + str(record_pos) + '&numRows=100&reverse=false',headers=payloadID, data=qconf_json, verify=False)
		record_pos += 100
		result_dict = result.json()
		for row in result_dict.get("return").get("rows"):
			for _, fields in row.items():
				ftime, event_count = fields
				event_total += int(event_count)
	if event_total > 0:
		append_sw_outputs_output("Events with today's date exist for the data source \'%s\'" %dsname)
		return 0
	else:
		append_sw_outputs_output("No events with today's date exist for the data source \'%s\', but the data source exists" %dsname)   
		return 1

def append_sw_outputs_output(output):
	sw_outputs.append({"OUTPUT": output})

def append_sw_outputs_attachment(filename, non_b64_attachment):
	sw_outputs.append({"attachment": {"filename": filename, "base64": base64.b64encode(non_b64_attachment)}})

#requests.packages.urllib3.disable_warnings(){}
no_error = True

try:
  	append_sw_outputs_output("Output not set")
	path = os.path.dirname(os.path.realpath(__file__))
	username = sw_context.inputs['NITROUSER']
	password = sw_context.inputs['NITROPASS']

	#Format to send encoded login information to nitro.
	#Authoritize = "Basic " + base64.b64encode(bytearray(username + ":" + password, "ascii")) #Seems to encode credentials correctly
	#auth_String = "Basic (" + base64.encodestring('%s:%s' % (username,password)) + ")"
	Authoritize = "Basic " + base64.b64encode(bytearray(username + ":" + password, "ascii")) + ")"
	#print(auth_String)
	payload = {"Authorization": Authoritize}
	#Actually will login to nitro with the credientials as well as get the sessionID
	mySession = requests.session()
	try:
		res = mySession.post("https://<url of ESM>/rs/esm/login", headers=payload, verify=False)#CRASHING HERE. CONNECTION ERROR
	except requests.exceptions.ConnectionError as e:
		append_sw_outputs_output("request failed. Error={}".format(str(e)))
		sys.exit()
	x = res.text.index('sessionID') + 10
	id = ""
	while res.text[x] != "<":
		id += res.text[x]
		x = x + 1
	#print(id)
	payloadID = {"Authorization": "Session " + id}

	#User inputs what type of search in Nitro they want to perform. These print statements just gives user information
	search = sw_context.inputs["QUERY"]


	#search based on the name of the data source
	if search == "name":
		sourceName = sw_context.inputs["DSNAME"]
		dsID = getDSid(sourceName)
		if dsID == "":
			append_sw_outputs_output("There is no data source with the name \'%s\' \n" %sourceName)
		else:
			qconf_json = build_config(dsID)
			qconf_json, total_records = query_esm(qconf_json)
			get_results(qconf_json, total_records, sourceName)
		
	#search nitro based on the ip of the data source 
	#8228 displayID seems to find all ip's so might be physical display's ID
	elif search == "ip":
		sourceIP = sw_context.inputs["DSIP"]
		DeviceTreeURL = "https://<url of ESM>/rs/esm/grpGetDeviceTreeEx?displayID=8228&hideDisabledDevices=true"
		deviceRes = requests.get(DeviceTreeURL, headers=payloadID, verify=False)
		windowsDict = json.loads(deviceRes.text)
		windowsDict1 = windowsDict.get("return")
		windowsDict2 = windowsDict1.get("devices")
		counter = 0
		foundID = ""
		while counter < len(windowsDict2):
			dict = windowsDict2[counter]
			for key in dict:
				if dict["ipAddress"] == sourceIP:
					foundID = dict["ipsID"]
			counter = counter + 1
		if foundID == "":
			append_sw_outputs_output("There is no data source with the IP Address \'%s\' \n" %sourceIP)
		else:
			qconf_json = build_config(foundID)
			qconf_json, total_records = query_esm(qconf_json)
			get_results(qconf_json, total_records, sourceIP)

	#Allows you to input a csv file and see if those data sources within the csv file are in nitro based on the ip		
	#Prints out the results to a csv file called csvResults.csv
	elif search == "csv":
		#print("hello")
		#csvInput = sw_context.inputs["CSVINPUT"]
		csvInput1 = open("c:\\scripts\\test.csv", "r")
		csvInput = csvInput1.read()
		nitroList = defaultdict(list)
		newfile = path + "\\CSV_INPUT.txt"
		if len(csvInput) < 1:
			no_error = False
			append_sw_outputs_output("No attached file, or attached file is blank")
		if(no_error):
			for f in csvInput:

				temp_file = open(newfile, "wb")
				temp_file.write(f)
				temp_file.close()

			with open(newfile) as g:
				nitroFile = csv.reader(g) #Reads the Nitro csv file
				for row in nitroFile: #Stores data from nitro file to the list
					for (i,j) in enumerate(row): 
						nitroList[i].append(j)
			ipColumn = sw_context.inputs["CCI"]
			nameColumn = sw_context.inputs["CCN"]
			ipColumnNum = int(ipColumn)
			nameColumnNum = int(nameColumn)
			ipListLen = len(nitroList[ipColumnNum])
			ipList = nitroList[ipColumnNum]
			dsList = nitroList[nameColumnNum]
			counterLen = 0


			with open(newfile, "w+b") as csvfile:
				fieldnames = ["dsname", "ip address", "events?"]
				writer =  csv.DictWriter(csvfile, fieldnames=fieldnames)
				writer.writeheader()
				DeviceTreeURL1 = "https://ashbnitroesm.bah.com/rs/esm/grpGetDeviceTreeEx?displayID=8228&hideDisabledDevices=true"
				
                
                nitro_conf = {"config": 
                                {
                                   "limit" : 100,
                                   "timeRange": time_range,
                                   "order": [{"direction": "ASCENDING",
                                              "field": {"name": "FirstTime"}
                                            }],
                                   "fields": [{"name": "ipAddress"},
                                               {"name" : "ipsID"}],
                                   "filters": [{"type": "EsmFieldFilter", 
                                                "field": {"name": "IPSID"},
                                                "operator": "IN","values": 
                                              [{"type": "ipAddress", "value":ipAddress_from_csv}]}]
                                    }         
                                }
                
                deviceRes1 = requests.get(DeviceTreeURL1, headers=payloadID, verify=False, data=nitro_conf)
                
                
                
				windowsDict00 = json.loads(deviceRes1.text)
				windowsDict01 = windowsDict00.get("return")
				windowsDict02 = windowsDict01.get("devices")
				while counterLen < ipListLen: #change to ipListLen when done doing small tests
					sourceIP = ipList[counterLen]
					counter1 = 0
					foundID = ""
					while counter1 < len(windowsDict02):
						dict1 = windowsDict02[counter1]
						for key in dict1:
							if dict1["ipAddress"] == sourceIP:
								foundID = dict1["ipsID"]
						counter1 = counter1 + 1
					if foundID == "":
						writer.writerow({"dsname": dsList[counterLen], "ip address": sourceIP, "events?": "No Data Source"})
						
					else:
						qconf_json = build_config(foundID)
						qconf_json, total_records = query_esm(qconf_json)
						ipStatus = get_results(qconf_json, total_records, sourceIP)
						if ipStatus == 0:
							writer.writerow({"dsname": dsList[counterLen], "ip address": sourceIP, "events?": "Yes"})
						else:
							writer.writerow({"dsname": dsList[counterLen], "ip address": sourceIP, "events?": "No"})
					counterLen = counterLen + 1
			#sw_outputs.append({"attachment": base64.b64encode("NoFile")})
			#sw_outputs.append({"output": "success"})
			#sw_output.append({"attachment": {"base64": base64.b64encode(csvfile), "filename":"csvResults.csv"}})
			with open(newfile, "rb") as new:
				content = new.read()
				append_sw_outputs_output("The results have been written and attached to this record")
				append_sw_outputs_attachment("csvResults_Processed.csv", content)
			#os.remove(newfile)

	#The type of search the user is trying to perform isn't supported. Throw this error message at them.
	else:
		append_sw_outputs_output("Invalid search, rerun program and enter a valid search")
		#sw_outputs.append({"attachment": base64.b64encode("NoFile"), "output": "Invalid search, rerun program and enter a valid search"})

	#append_sw_outputs("success")

	#Logout when program is done running.
	#done = requests.post('https://<url of ESM>/rs/esm/logout', headers=payloadID, verify=False)
except Exception as e:
	append_sw_outputs_output(str(e))
