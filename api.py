
from io import StringIO

from flask import Flask, request
from flask_restful import Resource, Api
from sqlalchemy import create_engine
import json
import os
import re
from io import StringIO
import click
import rsa
import string
import random
import pickle
from simplecrypt import encrypt, decrypt
import tsol
from engines.sql import SQL_Engine
from engines.cass_engine import Cassandra_Engine

KEY = None
ENGINE = Cassandra_Engine(['127.0.0.1'])

def error_payload(message):
	return {
		"status": "error",
		"data": None,
		"message": message
	}

def success_payload(data, message):
	return {
		"status": "success",
		"data": data,
		"message": message
	}

def clean(s):
	return re.sub('[^A-Za-z0-9]+', '', s)

def random_string(length):
    pool = string.ascii_letters + string.digits
    return ''.join(random.choice(pool) for i in range(length))

class NameRegistry(Resource):
	def get(self):
		if ENGINE.check_name(request.form['name']) == True:
			return error_payload('Name already registered.')
		else:
			return success_payload(None, 'Name available to register.')

	def post(self):
		if ENGINE.add_name(request.form['name'], request.form['n'], request.form['e']) == True:
			return success_payload(None, 'Name successfully registered.')
		else:
			return error_payload('Unavailable to register name.')

# GET does not require auth and just downloads packages. no data returns the DHT on IPFS or the whole SQL_Engine thing.
# POST required last secret. Secret is then flushed so auth is required again before POSTing again
class PackageRegistry(Resource):
	def get(self):
		# checks if the user can create a new package entry
		# if so, returns a new secret
		# user then must post the signed package to this endpoint
		if not ENGINE.check_package(request.form['owner'], request.form['package']):
			# try to pull the users public key
			query = ENGINE.get_key(request.form['owner'])

			# in doing so, check if the user exists
			if query == None:
				return error_payload('Owner does not exist.')

			# construct the user's public key
			user_public_key = rsa.PublicKey(int(query[0]), int(query[1]))

			# create a new secret
			secret = random_string(53)

			# sign and store it in the db so no plain text instance exists in the universe
			server_signed_secret = str(rsa.encrypt(secret.encode('utf8'), KEY[0]))
			query = ENGINE.set_secret(request.form['owner'], server_signed_secret)

			# sign and send secret to user
			user_signed_secret = rsa.encrypt(secret.encode('utf8'), user_public_key)
			return success_payload(str(user_signed_secret), 'Package available to register.')

		else:
			return error_payload('Package already exists.')

	def post(self):
		payload = {
			'owner' : request.form['owner'],
			'package' : request.form['package'],
			'data' : request.form['data']
		}

		owner = request.form['owner']
		package = request.form['package']
		data = request.form['data']
		b = ENGINE.get_named_secret(owner)
		print(b)
		secret = rsa.decrypt(eval(b), KEY[1])

		# data is a python tuple of the templated solidity at index 0 and an example payload at index 1
		# compilation of this code should return true
		# if there are errors, don't commit it to the db
		# otherwise, commit it
		raw_data = decrypt(secret, eval(data))
		package_data = json.loads(raw_data.decode('utf8'))
		'''
		payload = {
			'tsol' : open(code_path[0]).read(),
			'example' : example
		}
		'''

		# assert that the code compiles with the provided example
		tsol.compile(StringIO(package_data['tsol']), package_data['example'])

		template = pickle.dumps(package_data['tsol'])
		example = pickle.dumps(package_data['example'])

		if ENGINE.add_package(owner, package, template, example) == True:
			return success_payload(None, 'Package successfully uploaded.')
		return error_payload('Problem uploading package. Try again.')

class Packages(Resource):
	def get(self):
		data = ENGINE.get_package(request.form['owner'], request.form['package'])

		if data == None or data == False:
			return error_payload('Could not find package.')

		return success_payload(data, 'Package successfully pulled.')


app = Flask(__name__)
api = Api(app)

api.add_resource(NameRegistry, '/names')
api.add_resource(Packages, '/packages')
api.add_resource(PackageRegistry, '/package_registry')
	
if __name__ == '__main__':
	(pub, priv) = rsa.newkeys(512)
	KEY = (pub, priv)
	app.run(debug=True)
