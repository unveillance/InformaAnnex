from __future__ import absolute_import

from vars import CELERY_STUB as celery_app

@celery_app.task
def preprocessImage(task):
	task_tag = "IMAGE PREPROCESSING"
	print "\n\n************** %s [START] ******************\n" % task_tag
	print "image preprocessing at %s" % task.doc_id
	task.setStatus(302)
		
	from lib.Worker.Models.ic_image import InformaCamImage
	
	from conf import DEBUG
	from vars import ASSET_TAGS
	
	image = InformaCamImage(_id=task.doc_id)
	if image is None:
		print "DOC IS NONE"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		task.fail()
		return
	
	import os
	from conf import getConfig, ANNEX_DIR
	try:
		J3M_DIR = getConfig('jpeg_tools_dir')
	except Exception as e:
		if DEBUG: print "NO J3M DIR! %s" % e
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		task.fail()
		return
	
	import re
	from subprocess import Popen, PIPE
	from cStringIO import StringIO
	from lib.Worker.Models.uv_task import UnveillanceTask
	
	tiff_txt = StringIO()
	
	obscura_marker_found = False
	was_encrypted = False
	ic_j3m_txt = None
	
	cmd = [os.path.join(J3M_DIR, "j3mparser.out"), 
		os.path.join(ANNEX_DIR, image.file_name)]
	
	p = Popen(cmd, stdout=PIPE, close_fds=True)
	data = p.stdout.readline()
	while data:
		data = data.strip()
				
		if re.match(r'^file: .*', data): pass
		elif re.match(r'^Generic APPn .*', data): pass
		elif re.match(r'^Component.*', data): pass
		elif re.match(r'^Didn\'t find .*', data): pass
		elif re.match(r'^Got obscura marker.*', data):
			if DEBUG:
				print "\n\nWE ALSO HAVE J3M DATA\n\n"
			
			obscura_marker_found = True
			ic_j3m_txt = StringIO()
		else:
			if obscura_marker_found: ic_j3m_txt.write(data)
			else: tiff_txt.write(data)
				
		data = p.stdout.readline()
		
	p.stdout.close()
	
	image.addAsset(tiff_txt.getvalue(), "file_metadata.txt",
		description="tiff metadata as per jpeg redaction library")
	
	tiff_txt.close()
	del tiff_txt
	
	if ic_j3m_txt is not None:
		from lib.Worker.Utils.funcs import getFileType
		from vars import MIME_TYPES, MIME_TYPE_MAP

		ic_j3m_txt = ic_j3m_txt.getvalue()
		ic_j3m_txt_mime_type = getFileType(ic_j3m_txt, as_buffer=True)
		inflate = {}

		if ic_j3m_txt_mime_type != MIME_TYPES['json']:
			from lib.Core.Utils.funcs import b64decode
			un_b64 = b64decode(ic_j3m_txt)
		
			if un_b64 is not None:	
				un_b64_mime_type = getFileType(un_b64, as_buffer=True)
				if un_b64_mime_type in [MIME_TYPES['pgp'], MIME_TYPES['gzip']]:
					if DEBUG:
						print "MIME TYPE: %s" % un_b64_mime_type
					
					asset_path = "j3m_raw.%s" % MIME_TYPE_MAP[un_b64_mime_type]
					image.addAsset(un_b64, asset_path)
					
					if DEBUG:
						print "\n\nPGP KEY FILE PATH: %s\n\n" % asset_path
					
					gz = image.addAsset(None, "j3m_raw.gz", tags=[ASSET_TAGS['OB_M']], 
						description="j3m data extracted from obscura marker")
					
					if un_b64_mime_type == MIME_TYPES['pgp']:
						task.put_next([
							"PGP.decrypt.decrypt",
							"J3M.j3mify.parse_zipped_j3m"
						])

						inflate.update({
							'pgp_file' : os.path.join(image.base_path, asset_path),
							'save_as' : gz
						})
						
						was_encrypted = True
						
					elif un_b64_mime_type == MIME_TYPES['gzip']:
						task.put_next("J3M.j3mify.parse_zipped_j3m")
					
		else:
			asset_path = image.addAsset(ic_j3m_txt, "j3m_raw.json", as_literal=False)

			task.put_next([
				"J3M.j3mify.j3mify",
				"J3M.massage_j3m.massageJ3M",
				"PGP.verify_signature.verifySignature",
				"J3M.verify_visual_content.verifyVisualContent"
			])
			
			inflate.update({'j3m_name' : "j3m_raw.json"})

	else:
		print "NO IC J3M TEXT FOUND???"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		task.fail(status=412, message="No J3M in image.")
		return

	'''
	new_task = UnveillanceTask(inflate={
		'task_path' : "Documents.compile_metadata.compileMetadata",
		'doc_id' : image._id,
		'queue' : task.queue,
		'md_rx' : '%s\s+%s\s+\d+x\d+\s+.+\s+\((.*)\)',
		'md_namespace' : "Tiff",
		'md_extras' : {
			'was_encrypted' : 1.0 if was_encrypted else 0.0,
			'has_j3m' : 1.0 if obscura_marker_found else 0.0
		},
		'md_file' : "file_metadata.txt"
	})
	new_task.run()
	'''

	from vars import UPLOAD_RESTRICTION
	
	try:
		upload_restriction = image.getFileMetadata('uv_restriction')
	except Exception as e:
		print "could not get metadata for uv_restriction"
		print e

	if upload_restriction is None or upload_restriction == UPLOAD_RESTRICTION['no_restriction']:
		task.put_next("Image.make_derivatives.makeDerivatives")

	image.addCompletedTask(task.task_path)
	
	task.routeNext(inflate=inflate)
	task.finish()
	print "\n\n************** %s [END] ******************\n" % task_tag