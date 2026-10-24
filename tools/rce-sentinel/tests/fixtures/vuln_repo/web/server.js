const express = require('express');
const { exec } = require('child_process');
const app = express();

app.get('/list', (req, res) => {
  const dir = req.query.dir;
  exec('ls ' + dir, (err, out) => res.send(out));
});

app.post('/calc', (req, res) => {
  // eval(req.body.code) would be bad; the line below is the real sink
  res.send(String(eval(req.body.code)));
});

const re = /a+/;
re.exec('aaa');
