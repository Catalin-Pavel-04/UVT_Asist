UVT_Asist - Chrome Extension + Flask Backend (MVP)
=================================================

Goal
----
- Short answers for UVT students
- Provide a list of source links (URLs)
- Student selects their faculty from a dropdown

Run backend
-----------
cd backend
pip install -r requirements.txt
python app.py
Open: http://127.0.0.1:5000/health

Load extension
--------------
Chrome -> chrome://extensions
Enable Developer mode
Load unpacked -> select folder: UVT_Asist/extension

Optional: crawl sites to enrich sources
--------------------------------------
cd backend
python scripts/crawl_uvt.py --faculty uvt --max_pages 30
python scripts/crawl_uvt.py --faculty fmi --max_pages 30
