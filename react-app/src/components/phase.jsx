function Phase(props) {
  return (
    <div className="card">
      <div className="card-header has-background-white-ter">
        <p className="card-header-title">{props.title}</p>
      </div>
      <div className="card-content">
        {props.children}
      </div>
    </div>
  );
}

export default Phase;
