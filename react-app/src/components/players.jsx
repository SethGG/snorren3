function Players(props) {
  const m = (props.info.length > 2) ? props.info.length : 3;
  const tan = Math.tan(Math.PI/m);

  return (
    <div className="players has-background-white-ter card" style={{"--m": m, "--tan": tan}}>
      <div className="is-flex is-flex-direction-column is-justify-content-center is-align-items-center">
        <img className="fire-img" src={require('../images/fire.png').default} />
      </div>
      {props.info.map((player, index) =>
        <div className="is-flex is-flex-direction-column is-justify-content-center is-align-items-center" style={{"--i": index}}>
          <img className="role-img" src={require(`../images/${player.role}.png`).default} />
          <p>{player.name}</p>
        </div>
      )}
    </div>
  );
}

export default Players;
