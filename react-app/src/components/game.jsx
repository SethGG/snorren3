import {useEffect, useState, useRef} from 'react';
import Players from './players'
import Join from './join'

const WebSocketWrapper = function(url_func) {
  let ws;
  let should_reconnect = true;
  const callbacks = {};

  const startWebSocket = () => {
    ws = new WebSocket(url_func());
    ws.onmessage = (evt) => {
      const json = JSON.parse(evt.data);
      dispatch(json.event, json.data);
    };
    ws.onclose = () => {
      dispatch('close', null);
      setTimeout(startWebSocket, 5000);
    };
    ws.onopen = () => {
      dispatch('open', null);
    };
  };

  startWebSocket();

  this.bind = (event_name, callback) => {
    callbacks[event_name] = callbacks[event_name] || [];
    callbacks[event_name].push(callback);
  };
  this.send = (event_name, event_data) => {
    const payload = JSON.stringify({event: event_name, data: event_data});
    ws.send(payload);
  };
  this.close = () => {
    should_reconnect = false;
    ws.close();
  };

  const dispatch = (event_name, message) => {
    const chain = callbacks[event_name];
    if (typeof chain == 'undefined') return;
    chain.forEach((callback) => {callback(message);});
  };
};

const Game = () => {
  console.log("game render");
  const [websocket, setWebSocket] = useState(null);
  const con_id = useRef(null);

  useEffect(() => {
    const ws = new WebSocketWrapper( () => (
      `ws://${window.location.host}/ws` + (con_id.current ? `?id=${con_id.current}` : '')));
    ws.bind('id', (data) => {
      console.log(data);
      con_id.current = data;
    });
    setWebSocket(ws);
    return () => websocket.close();
  }, []);

  return (
    <section className="section is-medium">
      <div className="container is-max-desktop">
        <div className="columns is-mobile is-multiline is-centered">
          <div className="column is-narrow" id="players">
            <Players websocket={websocket} />
          </div>
          <div className="column is-full-touch" id="phase">
            <Join />
          </div>
        </div>
      </div>
    </section>
  );
};

export default Game;
