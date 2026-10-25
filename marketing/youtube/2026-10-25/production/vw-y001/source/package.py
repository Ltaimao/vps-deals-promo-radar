from pathlib import Path
from PIL import Image
import hashlib,json,shutil,subprocess,re,difflib,textwrap,datetime
P=Path('/workspace/work/youtube-production/vw-y001');R=Path('/workspace/work/seo15/vps-deals-promo-radar-main');Y=R/'marketing/youtube/2026-10-25';D=Y/'production/vw-y001';D.mkdir(parents=True,exist_ok=True);(D/'source').mkdir(exist_ok=True);(Y/'handoffs').mkdir(exist_ok=True)
def dump(p,a):p.write_text(json.dumps(a,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stamp(t):
 ms=round(max(t,0)*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
asr=json.loads((P/'asr.json').read_text());ref=(P/'narration.txt').read_text().split();words=[w for s in asr['segments'] for w in s['words']]
norm=lambda s:re.sub('[^a-z0-9]','',s.lower())
a=[norm(w) for w in ref];b=[norm(w['word']) for w in words];mapping={}
for block in difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks():
 for j in range(block.size):mapping[block.a+j]=words[block.b+j]
for i in range(len(ref)):
 if i not in mapping:
  l=max((j for j in mapping if j<i),default=None);r=min((j for j in mapping if j>i),default=None)
  if l is not None and r is not None:t=mapping[l]['end']+(mapping[r]['start']-mapping[l]['end'])*(i-l)/(r-l)
  elif l is not None:t=mapping[l]['end']+.15
  else:t=0
  mapping[i]={'start':t,'end':t+.18}
cues=[];k=0
while k<len(ref):
 end=k+1
 while end<len(ref) and end-k<12 and len(' '.join(ref[k:end+1]))<80 and not (end-k>=5 and ref[end-1].endswith(('.','?','!'))):end+=1
 while end-k>5 and re.sub(r'[^a-z]', '',ref[end-1].lower()) in {'a','the','of','and','to','with','for','your','our','its','is','do','not','from','by','more','than','what','how','this','different'}:end-=1
 line=' '.join(ref[k:end]).replace('vpsdealswire dot com','vpsdealswire.com');start=max(0,mapping[k]['start']);finish=max(start+.5,mapping[end-1]['end']);cues.append((start,finish,'\n'.join(textwrap.wrap(line,width=43))));k=end
srt='\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{t}' for i,(a,b,t) in enumerate(cues))+'\n';(P/'vw-y001.en.srt').write_text(srt)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(P/'vw-y001.mp4')]));dump(P/'ffprobe.json',probe)
video=P/'vw-y001.mp4';thumb=P/'thumbnail.jpg';sub=P/'vw-y001.en.srt'
(R/'static/videos').mkdir(exist_ok=True);shutil.copy2(video,R/'static/videos/vw-y001.mp4');shutil.copy2(thumb,R/'static/vw-y001-thumbnail.jpg');shutil.copy2(sub,R/'static/vw-y001.en.srt')
for f in ['narration.txt','asr.json','timing.json','video-timing.json','screen-recording.json','ffprobe.json','audio-levels.log','vw-y001.en.srt']:shutil.copy2(P/f,D/f)
for f in ['guide-top.png','guide-section-1.png','final-contact.jpg']:
 img=Image.open(P/f).convert('RGB');img.save(D/(Path(f).stem+'.webp'),quality=85)
for src,dest in [('record-vps.cjs','record-vps.cjs'),('synthesize-vps.py','synthesize.py'),('render-vps.py','render.py'),('asr-vps.py','transcribe.py'),('package-vps.py','package.py')]:shutil.copy2(P.parent/src,D/'source'/dest)
(D/'README.md').write_text('''# vw-y001 production evidence\n\nFinal MP4 lives in static/videos, thumbnail and English SRT in static/. Seven original designed scenes with a genuine public-guide recording. Source scripts are execution helpers; adjust workspace paths before reproduction. Do not commit voice model weights, caches or raw recordings.\n\nVoice: generic Piper en_US-ljspeech-high. Model repository MIT; LJ Speech dataset public domain. https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/ljspeech/high/MODEL_CARD and https://keithito.com/LJ-Speech-Dataset/ . No music, cloned individual voice, provider benchmark, price quote or external policy excerpt.\n\nAudio review is source-text plus final-track ASR, domain transcription, decode/signal checks. It is not a human listening claim. Captions use corrected source wording aligned to recognized word times; Muse can upload this optional English subtitle track.\n\nThe first capture tried a nonexistent /providers/ route; that recording was rejected and replaced. The final video uses only the successful guide recording referenced by screen-recording.json. The rejected directory screenshot is not delivered.\n''')
meta={'contentId':'vw-y001','mediaVersion':'v1','targetChannelId':'UCfgVJrtBJSeViu95AnaQxyA','title':'Shared vCPU VPS: Check Fair Use Before Buying','description':'https://www.vpsdealswire.com/articles/shared-vcpu-vps-fair-use/?utm_source=youtube&utm_medium=organic_video&utm_campaign=2026q4_youtube_vps&utm_content=vw-y001\n\nA vCPU count does not tell you how much sustained CPU use a VPS plan permits. This short buying guide explains three checks: resource allocation, written usage limits, and what happens when a workload reaches them.\n\nUse the fair-use checklist at VPS Deals Wire to narrow your shortlist, then confirm the actual product terms on the provider’s official page. This video is an educational checklist, not a benchmark, provider ranking or performance guarantee. The workload bars and Candidate A sheet are conceptual examples, not measured results or a quoted offer.\n\nNarration is synthesized; diagrams are original and the guide recording shows our real public website. Some official-site links on VPS Deals Wire are affiliate links; we may earn a commission at no extra cost to you.','language':'en','tags':['VPS','shared vCPU','CPU fair use','VPS buying guide','VPS Deals Wire'],'madeForKids':False,'format':'horizontal_video','proposedLocalDate':'2026-10-27','proposedTime':None,'timezone':'Asia/Shanghai','audienceNote':'Educational hosting buying guide, not specifically directed to children.','syntheticMediaNote':'Generic synthesized narration, original diagrams, actual website recording. Publisher must apply current YouTube disclosure guidance; do not claim real provider testing.','captionLanguage':'en','publishingOwner':'muse'};dump(D/'metadata.json',meta)
assets={'video':{'url':'https://www.vpsdealswire.com/videos/vw-y001.mp4','repositoryPath':'static/videos/vw-y001.mp4','sha256':sha(video),'bytes':video.stat().st_size,'durationSeconds':float(probe['format']['duration']),'width':1920,'height':1080,'fps':24,'videoCodec':'h264','audioCodec':'aac','audioRate':48000},'thumbnail':{'url':'https://www.vpsdealswire.com/vw-y001-thumbnail.jpg','repositoryPath':'static/vw-y001-thumbnail.jpg','sha256':sha(thumb),'bytes':thumb.stat().st_size,'width':1280,'height':720},'captions':{'url':'https://www.vpsdealswire.com/vw-y001.en.srt','repositoryPath':'static/vw-y001.en.srt','sha256':sha(sub),'bytes':sub.stat().st_size,'language':'en'}}
qa={'contentId':'vw-y001','checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mediaVersion':'v1','readyForHosting':True,'readyForPublisher':False,'youtubeUploadedByUs':False,'publishingOwner':'muse','visualReview':{'nineFinalFrameSamplesReviewed':True,'thumbnailFullSizeReviewed':True,'mobileContactSheetReviewed':True,'originalIllustrativeGraphics':True,'realWebsiteRecording':True,'no404InDeliveredRecording':True,'noTextClippingObserved':True,'noBenchmarkOrProviderPriceClaim':True,'editorialScore':87,'scoreNote':'Internal quality assessment, not measured CTR or promised effectiveness.'},'audioReview':{'method':'Source script + ASR of final encoded track + full decode and signal checks; no human audition claimed.','wordSequenceSimilarity':asr['wordSequenceSimilarity'],'spokenDomainRecognized':'vpsdealswire.com','genericSynthesizedNarration':True,'model':'en_US-ljspeech-high','datasetLicense':'public domain','music':False,'noClippingObserved':True},'facts':{'guideHttpStatus':200,'guideCapturedAt':json.loads((P/'screen-recording.json').read_text())['capturedAt'],'source':'https://www.vpsdealswire.com/articles/shared-vcpu-vps-fair-use/','externalProviderFactsUsed':False},'assets':assets,'publicHostingVerified':False,'channelIdentityAndDuplicateCheck':'Muse responsibility before upload','youtubeVideoId':None,'youtubeUrl':None,'actualPublishedAt':None};dump(D/'qa.json',qa)
handoff={'contentId':'vw-y001','mediaVersion':'v1','ready_for_publisher':False,'state':'media_qa_passed_awaiting_public_host_verification','ourRole':'content_and_publication_plan','publishingOwner':'muse','ourYouTubePublishingEnabled':False,'assets':assets,'metadata':meta,'qaRecord':'../production/vw-y001/qa.json','expectedReceipt':'../records/muse-vw-y001.json','deduplicationKeys':['contentId','mediaVersion','assets.video.sha256','targetChannelId','landing-page slug'],'publishInstructions':'Verify channel, reconcile current uploads/attempts before upload. Preserve existing videos. Scheduled is not published; return actual public video ID/URL/time.','youtubeVideoId':None,'youtubeUrl':None,'actualPublishedAt':None,'review7At':None,'review28At':None};dump(Y/'handoffs/vw-y001.json',handoff)
f=Y/'queue.json';q=json.loads(f.read_text());q['publishingOwner']='muse'
for x in q['items']:
 x['publishingOwner']='muse'
 if x['contentId']=='vw-y001':x.update(state=handoff['state'],handoffState=handoff['state'],mediaVersion='v1',handoff='handoffs/vw-y001.json',assets=assets);x['review']['mediaApproved']=True
f.write_text(json.dumps(q,indent=2,ensure_ascii=False)+'\n')
f=Y/'publication-plan.json';q=json.loads(f.read_text());q['publishingOwner']='muse'
for x in q['items']:
 x['publishingOwner']='muse'
 if x['contentId']=='vw-y001':x.update(mediaState=handoff['state'],handoff='handoffs/vw-y001.json',videoSourceUrl=assets['video']['url'],mediaSha256=assets['video']['sha256'],thumbnailUrl=assets['thumbnail']['url'])
dump(f,q)
f=Y/'scripts/vw-y001.md';s=f.read_text().replace('State: final media in production; YouTube publication owner: Muse.','State: media QA passed; awaiting verified public hosting. Publication owner: Muse.');f.write_text(s)
print(json.dumps({'assets':assets,'captionCues':len(cues),'duration':probe['format']['duration']}))
