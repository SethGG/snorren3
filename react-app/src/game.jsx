import Players from './players'

function Game() {
  return (
    <section className="section">
      <div className="container is-max-desktop">
        <div className="columns is-mobile is-multiline is-centered">
          <div className="column is-narrow" id="players">
            <Players info={[]} />
          </div>
          <div className="column is-full-touch" id="phase">
          </div>
        </div>
      </div>
    </section>
  );
}

export default Game;
