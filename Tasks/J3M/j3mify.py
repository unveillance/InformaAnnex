from __future__ import absolute_import

from vars import CELERY_STUB as celery_app

@celery_app.task
def j3mify(task):
	task_tag = "J3MIFYING"
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
		
	j3m_gz = media.loadAsset("j3m_raw.gz")
	if j3m_gz is None:
		print "NO J3M.GZ"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		return
	
	from cStringIO import StringIO
	from lib.Worker.Utils.funcs import getFileType, unGzipBinary
	
	j3m = unGzipBinary(j3m_gz)
	if j3m is None or getFileType(j3m, as_buffer=True) != MIME_TYPES['json']:
		print "THIS IS NOT A J3M"
		print "\n\n************** %s [ERROR] ******************\n" % task_tag
		return
	
	try:
		j3m_sig = json.loads(j3m)['signature']
	except KeyError as e:
		print "NO SIGNATURE TO EXTRACT"
		print "\n\n************** J3MIFYING [ERROR] ******************\n"
		return
	
	media.addAsset("j3m.sig", j3m_sig, tags=[ASSET_TAGS['SIG']],
		description="The j3m's signature")
	
	front_sentinel = "{\"j3m\":"
	back_sentinel = ",\"signature\":"
	
	j3m = j3m[len(front_sentinel) : j3m.index(back_sentinel)]
	media.addAsset("j3m.json", j3m, tags=[ASSET_TAGS['J3M']],
		description="The j3m itself.")
	
	from lib.Worker.Models.uv_task import UnveillanceTask
	task_paths = ["PGP.verify_signature.verifySignature",
		"J3M.verify_visual_content.verifyVisualContent"]

	for task_path in task_paths:
		next_task = UnveillanceTask(inflate={
			'task_path' : task_path,
			'doc_id' : media._id,
			'queue' : task.queue
		})
		next_task.run()
	
	task.finish()
	print "\n\n************** %s [END] ******************\n" % task_tag