import './players.css'
import fireImage from './assets/fire.png';

function Players(props) {
  const m = (props.info.length > 2) ? props.info.length : 3;
  const tan = Math.tan(Math.PI/m);

  return (
    <div className="players has-background-white-ter" style={{"--m": m, "--tan": tan}}>
      <div className="is-flex is-flex-direction-column is-justify-content-center is-align-items-center">
        <img className="fire-img" src={fireImage} alt="" />
      </div>
    </div>
  );
}

export default Players;
