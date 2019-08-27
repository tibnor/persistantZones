const WebSocket = require('ws');
var socket = new WebSocket("ws://192.168.1.92:8080", "gabbo");
socket.onmessage = function (event) {
  console.log(event.data)
};