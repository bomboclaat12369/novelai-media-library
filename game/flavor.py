"""Varied business copy without consuming the simulation's random draws."""
from .catalog import stable


EVENTS = {
    'booking': (
        ('One more sex booking?', "A customer is offering $55 for sex. Taking the booking costs one working host 10 energy."),
        ('A last-minute paid hookup', "Someone wants to get laid and has $55 ready. One working host spends 10 energy if you take the booking."),
        ('An extra $55 for sex', "A customer wants another paid sex appointment tonight. Take the $55 and spend 10 energy from a working host, or stick with the plan."),
        ('Can we fit in another sex booking?', "There is a $55 sex booking waiting at the front desk. A working host can take it for 10 energy."),
        ('A regular wants a paid hookup', "A regular is asking for sex and offering $55. One working host would need to put in another 10 energy. Your call."),
        ('A late sex booking lands', "A customer just asked about paying for sex tonight. The booking brings in $55 and costs one working host 10 energy."),
        ('A customer wants to get laid', "They are ready to pay $55 for a private sex appointment. It will take 10 energy from a working host."),
        ('Squeeze in another paid hookup?', "A customer has $55 ready for sex. One working host would need another 10 energy to cover the booking."),
    ),
    'hospitality': (
        ('Time for a quick break?', 'Put $25 toward refreshments and everyone working gets 12 energy back. Or keep the money handy.'),
        ('Get everyone a drink?', 'A $25 refreshment run gives each working team member 12 energy. Save the cash if you would rather push on.'),
        ('Give the team a breather', 'Spend $25 on a quick break for the working crew: 12 energy back each. Keeping the cash is fine too.'),
        ('A little fuel for the crew', 'Refreshments cost $25 and restore 12 energy to everyone working. Worth it tonight?'),
        ('Put something back into tonight', 'You can spend $25 to give the working team 12 energy each, or leave that cash in the till.'),
        ('Keep going or take five?', 'A $25 refreshment break restores 12 energy to each working person. Otherwise, carry on with the reserve intact.'),
        ('A round of refreshments?', 'The working crew can get 12 energy back for $25 total. Take the break or hang on to the cash.'),
        ('Make the next round a little easier', 'Put $25 into a team break and everyone working regains 12 energy. Or stick with what you have.'),
    ),
    'promotion': (
        ('Get the word out', 'A local feature costs $35. It adds two reputation and helps bring in bookings over the next three nights.'),
        ('Make a little noise', 'Spend $35 on local promotion for two reputation and better booking demand over the next three nights.'),
        ('Grab a spot in the local roundup', 'The feature is $35: two reputation and a booking boost over the next three nights. Or let word of mouth do its thing.'),
        ('Get a few more people talking', 'A $35 feature adds two reputation and improves booking demand over the next three nights.'),
        ('Put the place on the radar', 'Local promotion is available for $35. Take two reputation and better demand over the next three nights, or pass.'),
        ('A small push for the next few nights', 'Spend $35 on a feature to gain two reputation and lift booking demand over the next three nights.'),
        ('Give the front desk more to work with', 'A local feature costs $35 and adds two reputation, with better booking demand over the next three nights.'),
        ('Buy a little attention?', 'For $35, a local feature gives you two reputation and a demand boost over the next three nights. Up to you.'),
    ),
}

ACTIVITY = {
    'room': (
        'Another paid hookup wrapped up.', 'The sex booking is done and paid for.',
        'The customer got laid and settled the bill.', 'Another private sex appointment is over.',
        'They hooked up, and the customer paid.', 'One more paid hookup finished. On to the next booking.',
        'The latest sex booking is complete.', 'Another sex appointment finished and money in the till.',
    ),
    'lounge': (
        'Another lounge booking wrapped up.', 'The lounge brings in another payment.',
        'Another table is finished and paid up.', 'The next lounge booking is in the bag.',
        'The lounge keeps things moving.', 'One more lounge appointment sorted.',
        'The latest lounge customers settled up.', 'Another round in the lounge is done.',
    ),
    'studio': (
        'Another batch of shots is in the can.', 'The shoot keeps moving.',
        'The crew works through the next setup.', 'Another part of the shoot is sorted.',
        'The next set of shots is coming together.', 'The camera is rolling and the work is getting done.',
        'The crew is making headway on the project.', 'Another setup down. The shoot is on track.',
    ),
    'resort': (
        'The host is checking in on the guest.', 'The stay is ticking along nicely.',
        'The host takes care of the next part of the stay.', 'Another guest request gets handled.',
        'The guest has a host on hand.', 'The host keeps the stay running smoothly.',
        'The next part of the package is taken care of.', 'The host is staying on top of the booking.',
    ),
    'quiet': (
        'No booking landed this round.', 'A quiet spell. Nothing to bill this round.',
        'This slot went unfilled.', 'No customer took this round.',
        'Still waiting on the next booking.', 'No takers for this slot.',
        'A gap between bookings this time.', 'This round stayed quiet.',
    ),
    'tired': (
        'Running on fumes. A breather is needed.', 'Too worn out to cover this round properly.',
        'Energy is running too low for this one.', 'The pace is catching up. Time to recover.',
        'There is not enough energy for another full round.', 'A rest would help more than another booking right now.',
        'Out of steam for this round.', 'The shift is taking its toll. A break is due.',
    ),
    'round': (
        'The latest round is in.', 'Another round down.', 'Here is where the night stands.',
        'The next set of results is in.', 'A little further into the evening.',
        'The books have another round on them.', 'Time to tally the latest round.',
        'Another part of the evening is wrapped up.',
    ),
}


def event(kind, state):
    choices = EVENTS[kind]
    occurrence = (state['day'] - 1) // 2 if kind in ('booking', 'promotion') else state['day'] - 1
    title, detail = choices[(stable((state['seed'], 'event-copy', kind)) + occurrence) % len(choices)]
    return {'title': title, 'detail': detail}


def activity(kind, state, owner, wave):
    choices = ACTIVITY[kind]
    offset = stable((state['seed'], 'activity-copy', owner, kind))
    return choices[(offset + (state['day'] - 1) * 6 + wave - 1) % len(choices)]
