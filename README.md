# dj4xol
Duh-Jacks-Ohl
A classic turn based 4x space strategy game, implemented as a Django app. 
Players manage and expand an empire of stars and fleets of ships. The server
 will support multiple simultaneous games, invites to other players, email
 notifications, quorum based and scheduled turn generation. 
Currently just trying to get it to a basic playable state. 

## Demo Site
* git clone
* set up your venv/pyenv or whatever
* `pip install -r requirements.txt`
* `python manage.py migrate`
* `python manage.py runserver`
* site is available at localhost:8000/4x
