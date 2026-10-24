const express = require('express');
const { exec } = require('child_process');
const app = express();

app.get('/list', (req, res) => {
  const dir = req.query.dir;
  exec('ls ' + dir, (err, out) => res.send(out));
});
