
## Open Terminal
1. ```$ git clone https://github.com/Azure-Samples/python-docs-hello-world```
2. ```$ cd mb-text-donation```
3. ```$ python3 -m venv venv```
4. ```$ source venv/bin/activate```
5. ```$ pip install -r requirements.txt```
6. Export enviroment variables ```PUBLISHABLE_KEY``` and ```SECRET_KEY```
7. ```$ FLASK_APP=application.py flask run```

## Test
Navigate to [http://localhost:5000/500](http://localhost:5000/500) to test. replace 500 with any integer value.