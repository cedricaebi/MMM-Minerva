/* Magic Mirror
 * Module: MMM-Face-Reco-DNN
 *
 * By Thierry Nischelwitzer http://nischi.ch
 * MIT Licensed.
 */

const NodeHelper = require('node_helper')
const { PythonShell } = require('python-shell')
const onExit = require('signal-exit')
let pythonStarted = false
const Log = require('../../js/logger')
const io = require('socket.io-client')

const URL = 'http://localhost:5000'
const socket = io.io(URL, { autoConnect: true })

let previousEmotion = 'neutral'
let errorShown = false

module.exports = NodeHelper.create({
	pyshell: null,

	python_start: function () {
		Log.log('Starting node helper for: ' + this.name)
		const self = this
		const extendedDataset = this.config.extendDataset ? 'True' : 'False'
		const options = {
			mode: 'json',
			stderrParser: line => JSON.stringify(line),
			args: [
				'--cascade=' + this.config.cascade,
				'--encodings=' + this.config.encodings,
				'--usePiCamera=' + this.config.usePiCamera,
				'--source=' + this.config.source,
				'--rotateCamera=' + this.config.rotateCamera,
				'--method=' + this.config.method,
				'--detectionMethod=' + this.config.detectionMethod,
				'--interval=' + this.config.checkInterval,
				'--output=' + this.config.output,
				'--extendDataset=' + extendedDataset,
				'--dataset=' + this.config.dataset,
				'--tolerance=' + this.config.tolerance
			]
		}

		if (this.config.pythonPath != null && this.config.pythonPath !== '') {
			options.pythonPath = this.config.pythonPath
		}

		// Start face reco script
		self.pyshell = new PythonShell('modules/' + this.name + '/tools/facerecognition.py', options)

		//Check if server is reachable
		socket.on('connect_error', () => {
			if (errorShown === false) {
				self.sendSocketNotification('ERROR', {
					action: 'error',
					message: 'serverNotReachable'
				})
				errorShown = true
			}
		})

		//Define some socket listeners
		socket.on('connect', () => {
			console.log('[INFO] Socket connected with id: ' + socket.id)
			errorShown = false

			self.sendSocketNotification('ERROR', {
				action: 'error',
				message: 'serverReachable'
			})
		})

		socket.on('disconnect', () => {
			previousEmotion = 'neutral'

			self.sendSocketNotification('EMOTION', {
				action: 'emotion',
				emotion: previousEmotion
			})
		})

		socket.on('new_emotion', emotion => {
			if (previousEmotion !== emotion) {
				previousEmotion = emotion
				self.sendSocketNotification('EMOTION', {
					action: 'emotion',
					emotion: emotion
				})
			}
		})

		// check if a message of the python script is comming in
		self.pyshell.on('message', function (message) {
			// A status message has received and will log
			if (message.hasOwnProperty('status')) {
				console.log('[' + self.name + '] ' + message.status)
			}

			// Somebody new are in front of the camera, send it back to the Magic Mirror Module
			if (message.hasOwnProperty('login')) {
				console.log('[' + self.name + '] ' + 'Users ' + message.login.names.join(' - ') + ' logged in.')
				self.sendSocketNotification('USER', {
					action: 'login',
					users: message.login.names
				})
			}

			// Somebody left the camera, send it back to the Magic Mirror Module
			if (message.hasOwnProperty('logout')) {
				console.log('[' + self.name + '] ' + 'Users ' + message.logout.names.join(' - ') + ' logged out.')
				self.sendSocketNotification('USER', {
					action: 'logout',
					users: message.logout.names
				})
			}

			if (message.hasOwnProperty('prediction')) {
				socket.emit('predict', { pixels: message.prediction.pixelArray })
			}
		})

		// Shutdown node helper
		self.pyshell.end(function (err) {
			if (err) throw err
			console.log('[' + self.name + '] ' + 'finished running...')
		})

		onExit(function (code, signal) {
			self.destroy()
		})
	},

	python_stop: function () {
		this.destroy()
	},

	destroy: function () {
		console.log('[' + this.name + '] ' + 'Terminate python')
		this.pyshell.childProcess.kill()
	},

	socketNotificationReceived: function (notification, payload) {
		// Configuration are received
		if (notification === 'CONFIG') {
			this.config = payload
			// Set static output to 0, because we do not need any output for MMM
			this.config.output = 0
			if (!pythonStarted) {
				pythonStarted = true
				this.python_start()
			}
		}
	},

	stop: function () {
		pythonStarted = false
		this.python_stop()
	}
})
