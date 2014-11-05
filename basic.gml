graph [
  node [
    id s1
    isSwitch 1
  ]
  node [
    id s2
    isSwitch 1
  ]
  node [
    id s3
    isSwitch 1
  ]
  node [
    id s4
    isSwitch 1
  ]
  node [
    id h1
    isSwitch 0
  ]
  node [
    id h2
    isSwitch 0
  ]
  node [
    id h3
    isSwitch 0
  ]
  node [
    id h4
    isSwitch 0
  ]
  edge [
    source s1
    target s2
    bandwidth high
  ]
  edge [
    source s2
    target s3
    bandwidth high
  ]
  edge [
    source s3
    target s4
    bandwidth high
  ]
  edge [
    source s4
    target s1
    bandwidth high
  ]
  edge [
    source s1
    target h1
    bandwidth low
  ]
  edge [
    source s2
    target h2
    bandwidth low
  ]
  edge [
    source s3
    target h3
    bandwidth low
  ]
  edge [
    source s4
    target h4
    bandwidth low
  ]
]
