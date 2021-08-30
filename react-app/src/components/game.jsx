import Players from './players'
import Join from './join'

function Game() {
  return (
    <section className="section">
      <div className="container is-max-desktop">
        <div className="columns is-mobile is-multiline is-centered">
          <div className="column is-narrow" id="players">
            <Players info={[{name:"Henk", role:"burger"}, {name:"Fleur", role:"snor"}, {name:"Daniël"}, {name:"Marnix"}]} />
          </div>
          <div className="column is-full-touch" id="phase">
            <Join />
          </div>
        </div>
      </div>
    </section>
  );
}

export default Game;
