import {PropsWithChildren, useState} from "react"

import {Button, Divider, Modal, Select} from "antd"
import {createUseStyles} from "react-jss"

import {fetchTestset, useLoadTestsetsList} from "@/oss/services/testsets/api"

interface Props extends PropsWithChildren {
    onLoad: (tests: Record<string, string>[], shouldReplace: boolean) => void
}

const useStyles = createUseStyles({
    p: {
        marginBottom: 10,
    },
    select: {
        minWidth: 120,
        marginBottom: 20,
    },
    divider: {
        margin: "24px 0 0 0",
    },
})

const LoadTestsModal: React.FC<Props> = (props) => {
    const classes = useStyles()
    const {onLoad} = props
    const [isOpen, setIsOpen] = useState(false)
    const [selectedSet, setSelectedSet] = useState<string>("")

    const {testsets, isTestsetsLoading, isTestsetsLoadingError} = useLoadTestsetsList()

    const options = testsets?.map((item: Record<string, any>) => ({
        label: item.name,
        value: item._id,
    }))

    const handleClick = (shouldReplace: boolean) => {
        fetchTestset(selectedSet).then((data) => {
            onLoad(data.csvdata, shouldReplace)
        })
        setIsOpen(false)
    }

    return (
        <div>
            <Modal
                title="Load tests"
                open={isOpen}
                onCancel={() => setIsOpen(false)}
                footer={
                    <>
                        <Button disabled={!selectedSet} onClick={() => handleClick(false)}>
                            Add tests
                        </Button>
                        <Button disabled={!selectedSet} onClick={() => handleClick(true)}>
                            Replace tests
                        </Button>
                    </>
                }
            >
                <p className={classes.p}>Please select the test set you want to use:</p>

                <Select
                    className={classes.select}
                    options={options}
                    placeholder="Select data set"
                    onSelect={(id) => setSelectedSet(id)}
                />

                {selectedSet ? (
                    <>
                        <p>Click add test to add data to existing test</p>
                        <p>Click replace tests to replace data of existing tests</p>
                    </>
                ) : null}
                <Divider className={classes.divider} />
            </Modal>

            <Button
                type="default"
                size="middle"
                onClick={() => setIsOpen(true)}
                loading={isTestsetsLoading}
            >
                Load Test sets
            </Button>
        </div>
    )
}

export default LoadTestsModal
