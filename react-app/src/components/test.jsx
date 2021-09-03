import {useState, useEffect, useRef} from 'react';
import ReconnectingWebSocket from 'reconnecting-websocket';

const Chat = () => {
    const [messages, setMessages] = useState([]);
    const webSocket = useRef(null);

    useEffect(() => {
        webSocket.current = new ReconnectingWebSocket(`ws://${window.location.host}/ws`);
        webSocket.current.addEventListener('open', () => {
          console.log("connection opened")
        });
        webSocket.current.addEventListener('close', () => {
          console.log("connection closed")
        });
        webSocket.current.addEventListener('message', (message) => {
            setMessages(prev => [...prev, message.data]);
        });
        return () => webSocket.current.close();
    }, []);
    return <p>{messages.join(" ")}</p>;
};

export default Chat;
