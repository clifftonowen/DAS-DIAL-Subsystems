import React from 'react'
import { useState } from 'react'
import Table from './Table';

const [table, setTable] = useState(false);

export default function Graph() {
  return (
    <div>
      <div className='flex justify-between'>
        <div>dropdown</div>
        <div>dropdown</div>
        <div>dropdown</div>
      </div>
      <div>3 axis-Graph</div>
      <div className='flex justify-between' >
        <div onClick={setTable(!table)}>clickbale legends distinguished by colors</div>
        <div onClick={setTable(!table)}>clickbale legends distinguished by colors</div>
        <div onClick={setTable(!table)}>clickbale legends distinguished by colors</div>
      </div>

      <div><Table></Table></div>
    </div>

  )
}
