from __future__ import absolute_import

from vars import CELERY_STUB as celery_app

@celery_app.task
def massageJ3M(task):
	task_tag = "MASSAGING J3M"
	
	print "\n\n************** %s [START] ******************\n" % task_tag
	print "image preprocessing at %s" % task.doc_id
	task.setStatus(412)
		
	from lib.Worker.Models.uv_document import UnveillanceDocument
	
	from conf import DEBUG
	from vars import ASSET_TAGS
	
	media = UnveillanceDocument(_id=task.doc_id)
	if media is None:
		print "DOC IS NONE"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		return
	
	j3m = media.loadAsset("j3m.json")
	if j3m is None:
		print "J3M IS NONE"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		return
	
	from json import loads
	
	try:
		j3m = loads(j3m)
	except Exception as e:
		print "J3M IS INVALID"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		return
	
	from hashlib import sha1
	try:
		j3m['public_hash'] = sha1("".join(
			[j3m['genealogy']['createdOnDevice'],
			"".join(j3m['genealogy']['hashes'])])).hexdigest()
	except KeyError as e:
		if DEBUG: print "no key %s" % e
		pass
	
	try:
		location = j3m['data']['exif']['location']
		j3m['data']['exif']['location'] = [loc[1], loc[0]]
	except KeyError as e:
		if DEBUG: print "no key %s" % e
		pass
	
	try:
		if type(j3m['data']['sensorCapture']) is list: pass
	except KeyError as e:
		if DEBUG: print "no key %s" % e
		pass
	
	for playback in j3m['data']['sensorCapture']:
		try:
			gps = str(playback['sensorCapture']['gps_coords'])[1:-1].split(",")
			playback['sensorPlayback']['gps_coords'] = [float(gps[1]), float(gps[0])]
		except KeyError as e: pass
		
		try:
			gps = str(playback['sensorPlayback']['regionLocationData']['gps_coords'])
			gps = gps[1:-1].split(",")
			playback['sensorPlayback']['regionLocationData']['gps_coords'] = [
				float(gps[1]), float(gps[0])]
		except KeyError as e: pass
		
		try:
			for i,b in enumerate(playback['sensorPlayback']['visibleWifiNetworks']):
				playback['sensorPlayback']['visibleWifiNetworks'][i]['bt_hash'] = sha1(b['bssid']).hexdigest()
		except KeyError as e: pass
	
	import os
	from conf import getConfig
	from lib.Core.Utils.funcs import b64decode
	from lib.Worker.Utils.funcs import getFileType, unGzipStream

	try:
		with open(os.path.join(getConfig('forms_root'), "forms.json"), 'rb') as F:		
			for udata in j3m['data']['userAppendedData']:
				for aForms in udata['associatedForms']:
					for f in json.loads(F.read())['forms']:
						if f['namespace'] == aForms['namespace']:
							try:
								for mapping in f['mapping']:
									try:
										group = mapping.keys()[0]
										key = aForms['answerData'][group].split(" ")
										
										for m in mapping[group]:
											if m.keys()[0] in key:
												key[key.index(m.keys()[0])] = m[m.keys()[0]]
										aForms['answerData'][group] = " ".join(key)
									except KeyError as e:
										if DEBUG: print "no key %s" % e
										pass
							except KeyError as e:
								if DEBUG: print "no key %s" % e
								pass
							
							try:
								idx = 0
								for audio in f['audio_form_data']:
									try:
										audio_data = b64decode(
											aForms['answerData'][audio])
										
										if audio_data is None:
											if DEBUG: print "could not unb64 audio"
											continue
										
										if getFileType(audio_data, as_buffer=True) != MIME_TYPES['gzip']:
											if DEBUG: print "audio is not gzipped"
											continue
												
										audio_f = "audio_%d.3gp" % idx
										idx += 1
										
										media.addAsset(unGzipStream(audio_data), audio_f,
											tags=[ASSET_TAGS['A_3GP']],
											description="3gp audio file from form")
										
										new_task=UnveillanceTask(inflate={
											'task_path' : "Media.convert.audioConvert",
											'doc_id' : media._id,
											'formats' : ["3gp", "wav"],
											'src_file' : "audio_%d.3gp" % idx,
											'queue' : task.queue
										})
										new_task.run()
										
										aForms['answerData'][audio] = "audio_%d.wav"
									except KeyError as e:
										if DEBUG: print "no key %s" % e
										pass
							except KeyError as e:
								if DEBUG: print "no key %s" % e
								pass
	except KeyError as e:
		if DEBUG: print "no key %s" % e
		pass
										
	if media.addAsset(j3m, "j3m.json", as_literal=False) is not False:
		from lib.Worker.Models.ic_j3m import InformaCamJ3M
		
		j3m['media_id'] = media._id
		j3m = InformaCamJ3M(inflate=j3m)
		
		media.j3m_id = j3m._id
		media.save()
	
	task.finish()
	print "\n\n************** %s [END] ******************\n" % task_tag