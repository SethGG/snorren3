import React from 'react';
import ReactDOM from 'react-dom';
import Game from './components/game';
import Lobby from './components/lobby'
import './index.css';

ReactDOM.render(
  <React.StrictMode>
    <Game />
  </React.StrictMode>,
  document.getElementById('root')
);
